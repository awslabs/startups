# preflight_bedrock.py
"""Bedrock fail-fast preflight for an explicitly selected invocation API.

The selected API path is authoritative. Legacy callers that omit ``--api-path``
retain model-family inference, while an unknown non-empty path fails closed.
Every probe uses the requested Region and exact model ID.
"""
import argparse
import json
import sys


API_PATHS = {
    "runtime_openai_responses",
    "runtime_openai_chat",
    "runtime_messages",
    "mantle_openai_responses",
    "mantle_openai_chat",
    "mantle_messages",
    "runtime_converse",
    "runtime_invoke",
}
LEGACY_PATHS = {
    "converse": "runtime_converse",
    "gpt-oss": "runtime_converse",
    "mantle": "mantle_openai_responses",
}


def normalize_api_path(api_path: str | None) -> str | None:
    """Normalize documented legacy values; reject unknown non-empty values."""
    if api_path is None or not api_path.strip():
        return None
    path = api_path.strip()
    path = LEGACY_PATHS.get(path, path)
    if path not in API_PATHS:
        raise ValueError(f"unknown Bedrock API path: {api_path}")
    return path


def normalize_api_paths(api_paths: str | None, model_ids: list[str]) -> list[str | None]:
    """Align one path per model, allowing one shared legacy path for compatibility."""
    if api_paths is None or not api_paths.strip():
        return [None] * len(model_ids)
    supplied = [value.strip() for value in api_paths.split(",") if value.strip()]
    if len(supplied) == 1:
        supplied *= len(model_ids)
    if len(supplied) != len(model_ids):
        raise ValueError("API path count must be one or match the model count")
    return [normalize_api_path(path) for path in supplied]


def classify_invoke_error(code: str, message: str) -> dict:
    """Map a botocore error code to a structured preflight verdict."""
    if code == "AccessDeniedException":
        lowered = message.lower()
        if ("model access" in lowered or "access to the model" in lowered
                or "use the model" in lowered or "model is not" in lowered):
            return {"ok": False, "reason": "model_access",
                    "detail": f"Bedrock model access not enabled for this model — {message}. "
                              "Enable it in the Bedrock console (Model access page); "
                              "this is separate from IAM."}
        return {"ok": False, "reason": "authz",
                "detail": f"IAM denies bedrock:InvokeModel — {message}. "
                          "Grant bedrock:InvokeModel to this principal."}
    if code in ("ValidationException", "ResourceNotFoundException"):
        return {"ok": False, "reason": "model_unavailable",
                "detail": f"Model not available in this region — {message}. "
                          "Try a cross-region inference profile (e.g. us.<model-id>)."}
    if code in ("ThrottlingException", "ServiceQuotaExceededException"):
        return {"ok": True, "reason": "throttled_ok",
                "detail": "Authorized (probe throttled, which still proves access)."}
    if code in ("UnrecognizedClientException", "InvalidSignatureException",
                "ExpiredTokenException", "ExpiredToken"):
        return {"ok": False, "reason": "credentials",
                "detail": f"AWS credentials invalid or expired — {message}. "
                          "Run 'aws configure', refresh your SSO session, or set AWS_PROFILE."}
    return {"ok": False, "reason": "unknown", "detail": f"{code}: {message}"}


def classify_compatible_error(status: int | None, message: str, mantle: bool = False) -> dict:
    """Classify HTTP errors from OpenAI- and Anthropic-compatible endpoints."""
    if status in (401, 403):
        lowered = message.lower()
        if ("model access" in lowered or "access to the model" in lowered
                or "use the model" in lowered or "not authorized to use" in lowered):
            return {"ok": False, "reason": "model_access",
                    "detail": f"Bedrock model access not enabled for this model — {message}. "
                              "Enable it in the Bedrock console (Model access page); "
                              "this is separate from IAM."}
        if mantle:
            return {"ok": False, "reason": "authz",
                    "detail": f"IAM denies mantle inference — {message}. Grant bedrock-mantle "
                              "actions (for example CreateInference and CallWithBearerToken); "
                              "bedrock:InvokeModel does NOT authorize this endpoint."}
        return {"ok": False, "reason": "authz",
                "detail": f"IAM denies Bedrock Runtime compatible-API inference — {message}. "
                          "Grant bedrock:InvokeModel for the selected model/profile."}
    if status == 404:
        endpoint = "mantle endpoint" if mantle else "Runtime compatible endpoint"
        return {"ok": False, "reason": "model_unavailable",
                "detail": f"Model not available at this {endpoint}/region — {message}. "
                          "Verify the exact model ID, API support, and selected Region."}
    if status == 429:
        return {"ok": True, "reason": "throttled_ok",
                "detail": "Authorized (probe throttled, which still proves access)."}
    return {"ok": False, "reason": "unknown", "detail": f"{status}: {message}"}


def classify_mantle_error(status: int | None, message: str) -> dict:
    """Backward-compatible mantle classifier."""
    result = classify_compatible_error(status, message, mantle=True)
    if status == 404:
        result["detail"] = (
            f"Model not available at this mantle endpoint/region — {message}. Mantle is "
            "in-region only; verify the exact model/API pair or select a supported Runtime "
            "CRIS ID (us./in./global. when available). GPT-5.5/5.4 Runtime availability must "
            "be checked in the target account."
        )
    if status == 429:
        result["detail"] = (
            "Authorized (probe throttled on a token quota, which still proves access)."
        )
    return result


def is_embedding_model(model_id: str) -> bool:
    return "embed" in model_id.lower()


def is_mantle_model(model_id: str) -> bool:
    """Legacy inference used only when no explicit API path is supplied."""
    mid = model_id.lower()
    return mid.startswith("openai.gpt-5") and "oss" not in mid


def _status_code(exc) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return int(status) if status is not None else None


def _token_provider(region: str):
    from aws_bedrock_token_generator import provide_token
    return lambda: provide_token(region=region)


def runtime_openai_client(region: str, token_provider=None):
    from openai import OpenAI
    provider = token_provider or _token_provider(region)
    return OpenAI(
        base_url=f"https://bedrock-runtime.{region}.amazonaws.com/openai/v1",
        api_key=provider,
        max_retries=0,
    )


def mantle_openai_client(region: str, token_provider=None):
    from openai import OpenAI
    provider = token_provider or _token_provider(region)
    return OpenAI(
        base_url=f"https://bedrock-mantle.{region}.api.aws/openai/v1",
        api_key=provider,
        max_retries=0,
    )


def runtime_messages_client(region: str, token_provider=None, http_client=None):
    from anthropic import Anthropic
    provider = token_provider or _token_provider(region)
    kwargs = {
        "base_url": f"https://bedrock-runtime.{region}.amazonaws.com/anthropic",
        "auth_token": provider,
        "max_retries": 0,
    }
    if http_client is not None:
        kwargs["http_client"] = http_client
    return Anthropic(**kwargs)


def mantle_messages_client(region: str, token_provider=None, http_client=None):
    from anthropic import Anthropic
    provider = token_provider or _token_provider(region)
    kwargs = {
        "base_url": f"https://bedrock-mantle.{region}.api.aws/anthropic",
        "auth_token": provider,
        "max_retries": 0,
    }
    if http_client is not None:
        kwargs["http_client"] = http_client
    return Anthropic(**kwargs)


def probe_openai_responses(client, model_id: str) -> dict:
    response = client.responses.create(
        model=model_id, input="ping", max_output_tokens=16, store=False)
    return {"ok": True, "reason": "ok", "detail": "OpenAI Responses API authorized.",
            "response": response}


def probe_openai_chat(client, model_id: str) -> dict:
    response = client.chat.completions.create(
        model=model_id,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=16,
    )
    return {"ok": True, "reason": "ok", "detail": "OpenAI Chat Completions API authorized.",
            "response": response}


def probe_messages(client, model_id: str) -> dict:
    response = client.messages.create(
        model=model_id,
        max_tokens=16,
        messages=[{"role": "user", "content": "ping"}],
    )
    return {"ok": True, "reason": "ok", "detail": "Anthropic Messages API authorized.",
            "response": response}


def probe_compatible_model(model_id: str, region: str, api_path: str,
                           client_factory=None) -> dict:
    """Probe one compatible API path; factories are injectable for no-network tests."""
    mantle = api_path.startswith("mantle_")
    factories = {
        "runtime_openai_responses": runtime_openai_client,
        "runtime_openai_chat": runtime_openai_client,
        "runtime_messages": runtime_messages_client,
        "mantle_openai_responses": mantle_openai_client,
        "mantle_openai_chat": mantle_openai_client,
        "mantle_messages": mantle_messages_client,
    }
    probes = {
        "runtime_openai_responses": probe_openai_responses,
        "runtime_openai_chat": probe_openai_chat,
        "runtime_messages": probe_messages,
        "mantle_openai_responses": probe_openai_responses,
        "mantle_openai_chat": probe_openai_chat,
        "mantle_messages": probe_messages,
    }
    try:
        client = (client_factory or factories[api_path])(region)
        verdict = probes[api_path](client, model_id)
        verdict.pop("response", None)
        return verdict
    except ImportError as exc:
        return {"ok": False, "reason": "compatible_api_deps_missing",
                "detail": f"Cannot probe {api_path}: {exc}. Re-sync the pinned scripts environment; "
                          "access was NOT verified."}
    except Exception as exc:  # noqa: BLE001 - compatible SDK exception families vary
        status = _status_code(exc)
        if status is None:
            return {"ok": False, "reason": "credentials",
                    "detail": f"{type(exc).__name__}: {exc}. Check AWS credentials, Region, "
                              "and network access to the selected Bedrock endpoint."}
        return classify_compatible_error(status, str(exc), mantle=mantle)


def probe_mantle_model(model_id: str, region: str) -> dict:
    """Backward-compatible legacy mantle Responses probe."""
    verdict = probe_compatible_model(model_id, region, "mantle_openai_responses")
    if verdict["reason"] == "compatible_api_deps_missing":
        verdict["reason"] = "mantle_deps_missing"
    return verdict


def _embed_request_body(model_id: str) -> dict | None:
    parts = model_id.split(".")
    vendor = parts[1] if parts[0] in ("us", "eu", "apac", "global") and len(parts) > 1 else parts[0]
    if vendor == "amazon":
        return {"inputText": "ping"}
    if vendor == "cohere":
        return {"texts": ["ping"], "input_type": "search_document"}
    return None


def _invoke_request_body(model_id: str) -> dict:
    if is_embedding_model(model_id):
        return _embed_request_body(model_id) or {}
    return {"anthropic_version": "bedrock-2023-05-31", "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}]}


def probe_model(client, model_id: str, api_path: str = "runtime_converse") -> dict:
    """Probe Runtime Converse or InvokeModel with the exact model ID."""
    from botocore.exceptions import BotoCoreError, ClientError
    try:
        if is_embedding_model(model_id):
            body = _embed_request_body(model_id)
            if body is None:
                return {"ok": True, "reason": "embedding_unprobed",
                        "detail": "Embedding model from an unrecognized family — access not "
                                  "verified by preflight; confirm in the Bedrock console."}
            client.invoke_model(modelId=model_id, body=json.dumps(body),
                                contentType="application/json", accept="application/json")
            return {"ok": True, "reason": "ok", "detail": "InvokeModel (embedding) authorized."}
        if api_path == "runtime_invoke":
            client.invoke_model(modelId=model_id, body=json.dumps(_invoke_request_body(model_id)),
                                contentType="application/json", accept="application/json")
            return {"ok": True, "reason": "ok", "detail": "InvokeModel authorized."}
        client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "ping"}]}],
            inferenceConfig={"maxTokens": 1},
        )
        return {"ok": True, "reason": "ok", "detail": "Converse authorized."}
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        msg = exc.response.get("Error", {}).get("Message", str(exc))
        return classify_invoke_error(code, msg)
    except BotoCoreError as exc:
        return {"ok": False, "reason": "credentials",
                "detail": f"{type(exc).__name__}: {exc}. Run 'aws configure', refresh your "
                          "SSO session, or check the region name."}


def aggregate_failure(results: list) -> dict:
    failing = [result for result in results if not result["ok"]]
    if not failing:
        return {}
    return {"reason": failing[0]["reason"], "detail": failing[0]["detail"],
            "failing_models": [result["model_id"] for result in failing]}


def quota_rpm(quotas: list, model_id: str) -> int | None:
    tokens = [token for token in model_id.lower().replace(":", ".").split(".") if token]
    name_tokens = set()
    for token in tokens:
        name_tokens.update(part for part in token.split("-") if part and not part.isdigit())
    lowest = None
    for quota in quotas:
        name = quota.get("QuotaName", "").lower()
        if "per minute" not in name or "request" not in name:
            continue
        if not any(token in name for token in name_tokens):
            continue
        value = int(quota.get("Value", 0))
        lowest = value if lowest is None else min(lowest, value)
    return lowest


def fetch_bedrock_quotas(region: str) -> list:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    try:
        sq = boto3.client("service-quotas", region_name=region)
        quotas = []
        for page in sq.get_paginator("list_service_quotas").paginate(ServiceCode="bedrock"):
            quotas.extend(page.get("Quotas", []))
        return quotas
    except (BotoCoreError, ClientError):
        return []


def _quota_note(api_path: str) -> str:
    if api_path.startswith("mantle_"):
        return ("Mantle quotas are per-model input/output tokens per minute with no RPM quota; "
                "pace on token throughput and retry 429 responses with backoff.")
    if api_path in {"runtime_openai_responses", "runtime_openai_chat", "runtime_messages"}:
        return ("The selected Runtime compatible API uses Bedrock model/profile request and "
                "token quotas; monitor token throughput and retry throttling with backoff.")
    return ("Bedrock Runtime quotas can include requests and tokens per minute for the selected "
            "model/profile; pace evaluation traffic and retry throttling with backoff.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True)
    parser.add_argument("--models", required=True, help="comma-separated model ids")
    parser.add_argument(
        "--api-path",
        help="one selected migration_path or comma-separated paths aligned to --models; omitted for legacy inference",
    )
    parser.add_argument("--dataset-size", type=int, default=0)
    args = parser.parse_args(argv)

    model_ids = [model.strip() for model in args.models.split(",") if model.strip()]
    if not model_ids:
        print(json.dumps({"ok": False, "region": args.region, "models": [],
                          "reason": "no_models",
                          "detail": "--models resolved to an empty list; nothing to probe."}, indent=2))
        return 1
    try:
        selected_paths = normalize_api_paths(args.api_path, model_ids)
    except ValueError as exc:
        print(json.dumps({"ok": False, "region": args.region, "models": [],
                          "reason": "unknown_api_path", "detail": str(exc)}, indent=2))
        return 1

    import boto3
    from botocore.exceptions import BotoCoreError
    try:
        runtime_client = boto3.client("bedrock-runtime", region_name=args.region)
    except BotoCoreError as exc:
        print(json.dumps({"ok": False, "region": args.region, "models": [],
                          "reason": "credentials", "detail": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1

    quotas = fetch_bedrock_quotas(args.region)
    results = []
    all_ok = True
    for model_id, selected_path in zip(model_ids, selected_paths):
        legacy_inference = selected_path is None
        path = selected_path
        if path is None:
            path = "mantle_openai_responses" if is_mantle_model(model_id) else "runtime_converse"
        if legacy_inference and is_mantle_model(model_id):
            verdict = probe_mantle_model(model_id, args.region)
        elif is_embedding_model(model_id):
            verdict = probe_model(runtime_client, model_id, "runtime_invoke")
        elif path in {"runtime_converse", "runtime_invoke"}:
            verdict = probe_model(runtime_client, model_id, path)
        else:
            verdict = probe_compatible_model(model_id, args.region, path)
        verdict["model_id"] = model_id
        verdict["api_path"] = path
        verdict["rpm_quota"] = None if path.startswith("mantle_") else quota_rpm(quotas, model_id)
        verdict["quota_note"] = _quota_note(path)
        rpm = verdict["rpm_quota"]
        if rpm is not None and args.dataset_size > rpm:
            verdict["quota_warning"] = (
                f"Dataset ({args.dataset_size}) exceeds ~{rpm} RPM quota — "
                "Eval will pace with backoff and may be slow.")
        all_ok = all_ok and verdict["ok"]
        results.append(verdict)

    normalized_paths = [result["api_path"] for result in results]
    output = {
        "ok": all_ok,
        "region": args.region,
        "api_path": normalized_paths[0] if len(set(normalized_paths)) == 1 else None,
        "api_paths": normalized_paths,
        "probe_cost_note": "Minimal selected-API probe per model; usage is billable.",
        "models": results,
    }
    output.update(aggregate_failure(results))
    print(json.dumps(output, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
