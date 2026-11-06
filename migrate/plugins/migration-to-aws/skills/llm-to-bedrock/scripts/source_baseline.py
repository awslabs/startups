#!/usr/bin/env python3
"""Re-run each golden prompt against the customer's live source model.

Usage:
  SOURCE_MODEL_ID=<id> GOLDEN_DATASET_PATH=<jsonl> OUTPUT_PATH=<jsonl> \\
    python source_baseline.py <path/to/.source-provider-env>

Writes one JSON record per prompt to OUTPUT_PATH, preserving source and target route identity:
  {"id": ..., "source_provider": ..., "source_model": ..., "workload_id": ...,
   "call_site": ..., "aws_model_id": ..., "migration_path": ..., "model_change": ...,
   "source_response": "<text or empty>",
   "status": "live | http_<code>: <reason> | error: <type>: <message>"}

Partial-resume: prompts whose id already has a "live" row in OUTPUT_PATH are
skipped only when every source and target identity field still matches. A stale
row fails closed before any provider call so it cannot be silently relabeled;
failed rows are retried.

Security: the key is read from the env file into the process environment only
and sent ONLY as an auth header to its own provider's official endpoint
(api.openai.com / api.anthropic.com / generativelanguage.googleapis.com) —
never to any other host, never as a URL query parameter, never to stdout or
the output JSONL.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

# Requests intentionally use provider defaults for temperature/top_p — the
# golden dataset doesn't record per-request sampling params, and the same
# defaults-only shape is used for all three providers so the comparison is
# apples-to-apples. The 4096-token cap matches the Bedrock eval side.
MAX_TOKENS = 4096


def load_env_file(path: str) -> dict[str, str]:
    """Parse the env file and return ITS pairs. The file is authoritative for
    provider selection — an ambient OPENAI_API_KEY must not select OpenAI when
    the migration's file carries a GEMINI_API_KEY. Parsed pairs are also
    exported so the request builders read the file's values."""
    pairs: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and "=" in line:
                k, v = line.split("=", 1)
                pairs[k] = v
                os.environ[k] = v
    return pairs


def build_openai_request(model: str, system: str, user_text: str) -> tuple[str, dict, dict]:
    body = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else [])
        + [{"role": "user", "content": user_text}],
        # gpt-5.x rejects max_tokens (HTTP 400 unsupported_parameter) and
        # requires max_completion_tokens. The newer name is accepted by all
        # current models, so it is sent unconditionally.
        "max_completion_tokens": MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    }
    return "https://api.openai.com/v1/chat/completions", headers, body


def build_anthropic_request(model: str, system: str, user_text: str) -> tuple[str, dict, dict]:
    body = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": user_text}],
    }
    if system:
        body["system"] = system
    headers = {
        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    return "https://api.anthropic.com/v1/messages", headers, body


def build_gemini_request(model: str, system: str, user_text: str) -> tuple[str, dict, dict]:
    body = {
        "contents": [{"parts": [{"text": user_text}]}],
        "generationConfig": {"maxOutputTokens": MAX_TOKENS},
    }
    if system:
        # systemInstruction mirrors how the customer's app passes system
        # prompts — concatenating into the user turn would change behavior.
        body["systemInstruction"] = {"parts": [{"text": system}]}
    # Key travels as a header, not a query parameter — URLs end up in logs.
    headers = {
        "x-goog-api-key": os.environ["GEMINI_API_KEY"],
        "Content-Type": "application/json",
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    return url, headers, body


PROVIDER_TO_KEY = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def pick_provider_key(file_pairs: dict) -> str | None:
    """Select the provider key name. SOURCE_PROVIDER (the helper's declared
    input) is authoritative when set — a file carrying several provider keys
    must not fall back to dict-order guessing. Without it, fall back to the
    first recognized key IN THE FILE (never the ambient environment)."""
    stated = os.environ.get("SOURCE_PROVIDER", "").lower()
    if stated:
        key = PROVIDER_TO_KEY.get(stated)
        if key is None or key not in file_pairs:
            return None
        return key
    return next((k for k in PROVIDERS if k in file_pairs), None)


def _secret_variants(secrets) -> list:
    """Every textual form a secret can take in error text. A raw CR/LF inside
    a credential is rendered ESCAPED in exception messages (repr turns one
    control char into backslash-r text), so literal replacement alone misses
    it; the control-char-split fragments catch any remaining partial echo."""
    import re as _re
    out: list = []
    for s in secrets:
        if not s:
            continue
        out.append(s)
        esc = s.encode("unicode_escape").decode("ascii")
        if esc != s:
            out.append(esc)
        for frag in _re.split(r"[\x00-\x1f]+", s):
            if len(frag) >= 6 and frag not in out:
                out.append(frag)
    return sorted(out, key=len, reverse=True)


def redact(text: str, secrets) -> str:
    """Strip secret values from failure text. A raised exception can embed a
    header value verbatim (http.client rejects an invalid header with the full
    'Bearer <key>' in the ValueError message), and the docstring promise is
    that the key never reaches the output JSONL."""
    for s in _secret_variants(secrets):
        text = text.replace(s, "***")
    return text


PROVIDERS = {
    # env key → (request builder, response-text extractor)
    "OPENAI_API_KEY": (
        build_openai_request,
        lambda d: d["choices"][0]["message"]["content"],
    ),
    "ANTHROPIC_API_KEY": (
        build_anthropic_request,
        lambda d: d["content"][0]["text"],
    ),
    "GEMINI_API_KEY": (
        build_gemini_request,
        lambda d: d["candidates"][0]["content"]["parts"][0]["text"],
    ),
}


ERROR_BODY_CAP = 2048
AUTH_CODES = (401, 403)


def error_detail(e: urllib.error.HTTPError, secrets=()) -> str:
    """Bounded, credential-free extract of the provider's error body.

    The evaluator contract needs the HTTP 400 body's message/param to tell a
    request-shape bug from a quota or auth problem — reason alone is usually
    just "Bad Request" and the body is irrecoverable after this process exits.

    Auth errors (401/403) return no detail at all: their classification uses
    the status code alone, and an auth endpoint can echo the submitted
    credential in its body. Every remaining path is redacted against the known
    key values, including the non-JSON fallback.
    """
    if e.code in AUTH_CODES:
        return ""
    try:
        raw = e.read(ERROR_BODY_CAP).decode("utf-8", "replace")
    except Exception:
        return ""
    try:
        err = json.loads(raw).get("error", {})
        if isinstance(err, dict):
            msg = err.get("message", "")
            param = err.get("param")
            detail = f"{msg} (param: {param})" if param else msg
            return redact(detail, secrets)
    except (json.JSONDecodeError, AttributeError):
        pass
    return redact(raw[:200], secrets)


def _send(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310 — fixed https hosts
        return json.loads(resp.read())


def route_identity(prompt: dict) -> dict:
    """Copy the stable source and target route fields into every downstream row."""
    fields = (
        "source_provider", "source_model", "workload_id", "call_site",
        "aws_model_id", "migration_path", "model_change",
    )
    missing = [field for field in fields if field not in prompt or prompt[field] in (None, "")]
    if missing:
        raise ValueError(f"prompt {prompt.get('id', '<unknown>')} missing route attribution: {missing[0]}")
    return {field: prompt[field] for field in fields}


def _provider_key(source_provider: str, file_pairs: dict[str, str]) -> str | None:
    key = PROVIDER_TO_KEY.get(source_provider.lower())
    return key if key in file_pairs else None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    file_pairs = load_env_file(sys.argv[1])

    try:
        dataset_path = os.environ["GOLDEN_DATASET_PATH"]
        output_path = os.environ["OUTPUT_PATH"]
    except KeyError as e:
        print(f"FAIL: required env var {e} not set", file=sys.stderr)
        return 2

    file_provider = os.environ.get("SOURCE_PROVIDER", "").lower()
    model_override = os.environ.get("SOURCE_MODEL_ID")
    secrets = [v for k, v in file_pairs.items() if k in PROVIDERS]

    with open(dataset_path) as f:
        prompts = [json.loads(line) for line in f if line.strip()]
    try:
        identities = {prompt["id"]: route_identity(prompt) for prompt in prompts}
    except (KeyError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    source_routes = {
        (identity["source_provider"].lower(), identity["source_model"])
        for identity in identities.values()
    }
    if file_provider and any(provider != file_provider for provider, _ in source_routes):
        print("FAIL: SOURCE_PROVIDER does not match every golden row in this baseline batch",
              file=sys.stderr)
        return 2
    if model_override and len(source_routes) > 1:
        print("FAIL: SOURCE_MODEL_ID override requires one source route per baseline batch",
              file=sys.stderr)
        return 2
    for provider_name, _ in source_routes:
        if _provider_key(provider_name, file_pairs) is None:
            print(f"FAIL: no usable {provider_name} key in the env file", file=sys.stderr)
            return 2

    results = []
    done_live = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("status") != "live" or row.get("id") not in identities:
                    continue
                expected = identities[row["id"]]
                changed = [field for field, value in expected.items() if row.get(field) != value]
                if changed:
                    print(
                        f"FAIL: route attribution changed for baseline row {row['id']}: "
                        f"{changed[0]}; remove the stale row and refetch the live baseline",
                        file=sys.stderr,
                    )
                    return 2
                results.append(row)
                done_live.add(row["id"])
    prompts = [p for p in prompts if p["id"] not in done_live]
    if done_live:
        print(f"RESUME: {len(done_live)} live baselines kept, {len(prompts)} to fetch")

    for p in prompts:
        identity = route_identity(p)
        provider = _provider_key(identity["source_provider"], file_pairs)
        build, extract = PROVIDERS[provider]
        model = model_override or identity["source_model"]
        try:
            url, headers, body = build(model, p.get("system_prompt") or "", p["user_prompt"])
            out = extract(_send(url, headers, body))
            results.append({"id": p["id"], **identity,
                            "source_response": out, "status": "live"})
        except urllib.error.HTTPError as e:
            detail = error_detail(e, secrets)
            status = f"http_{e.code}: {e.reason}" + (f" — {detail}" if detail else "")
            results.append({"id": p["id"], **identity, "source_response": "",
                            "status": redact(status, secrets)})
        except Exception as e:  # noqa: BLE001 — every row must land in the JSONL
            results.append({"id": p["id"], **identity, "source_response": "",
                            "status": redact(f"error: {type(e).__name__}: {e}", secrets)})

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    ok = sum(1 for r in results if r["status"] == "live")
    print(f"live source baselines: {ok}/{len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
