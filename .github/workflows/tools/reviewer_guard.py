#!/usr/bin/env python3
"""Assert the invariants that let `agentcore-reviewer.yml` run on `pull_request_target`.

That trigger hands base-repository credentials to a job whose inputs a contributor
controls. It is acceptable only while both of these hold:

  1. Contributor code is never fetched into the credentialed runner.
  2. No fork-controlled value reaches a shell.

## Why this is an allowlist, and why it is not grep

The first version of this guard was two greps for bad patterns. Adversarial review wrote
sixteen hostile workflows against it: fifteen passed, and the one it rejected was the
safe `env:`-indirection pattern its own error message recommended. The bypasses were not
exotic:

  - `uses: "actions/checkout@v4"` defeated an anchored `uses:[[:space:]]*actions/checkout`.
  - A folded scalar (`uses: >-` then the value on the next line) defeated it again.
  - `${{ format('{0}', github.event.pull_request.title) }}` defeated a
    `\\$\\{\\{[^}]*title[^}]*\\}\\}` pattern, because the character class cannot cross the
    `}` inside `{0}`.
  - Indirection defeated it wholesale: a local composite action, a reusable workflow, or
    `gh pr checkout` in a `run:` body all fetch fork code with no `actions/checkout`.
  - Fields a denylist has to remember were simply absent: `head.label`,
    `head.repo.description`, bracket spellings like `head['ref']`, and
    `toJSON(github.event)`, which embeds the title and body wholesale.

Enumerating bad YAML is unwinnable, so this enumerates good YAML. Anything not
explicitly permitted fails, so new syntax, new fields, and new spellings fail closed.
That is the only property that matters for a control whose failure mode is a credential
exposure rather than a broken build.

The YAML tree is parsed rather than pattern-matched, so quoting, folded scalars, and key
order cannot change the answer.

Usage: reviewer_guard.py <workflow.yml> [...]
Exit 0 when every file satisfies the invariants, 1 on a violation or an unusable file,
2 on a usage error.
"""

from __future__ import annotations

import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    print("::error::PyYAML is unavailable, so the reviewer guard cannot run.", file=sys.stderr)
    raise SystemExit(1)

# Actions the reviewer may use, pinned by digest. An allowlist rather than a checkout
# denylist, because many actions can fetch code. A local action (`./...`) is never
# allowed: its contents come from the same ref as the workflow, so on the fork arm it is
# contributor-authored code.
ALLOWED_USES = {
    "aws-actions/configure-aws-credentials@b47578312673ae6fa5b5096b330d9fbac3d116df",
}

# Expressions the reviewer may interpolate. Each is base-controlled or structurally
# unable to carry an injection: a sha is hex, a number is an integer, and `vars`,
# `secrets`, and `github.token` are repository configuration.
ALLOWED_EXPRESSIONS = [
    re.compile(p)
    for p in (
        r"^github\.event\.pull_request\.head\.sha$",
        r"^github\.event\.pull_request\.number$",
        r"^github\.event\.pull_request\.base\.ref$",
        r"^github\.event\.repository\.default_branch$",
        r"^github\.event_name$",
        r"^github\.repository$",
        r"^github\.ref$",
        r"^github\.ref_name$",
        r"^github\.run_id$",
        r"^github\.run_attempt$",
        r"^github\.token$",
        r"^github\.server_url$",
        r"^vars\.[A-Za-z0-9_]+$",
        r"^secrets\.[A-Za-z0-9_]+$",
        r"^steps\.[A-Za-z0-9_-]+\.outputs\.[A-Za-z0-9_-]+$",
        r"^env\.[A-Za-z0-9_]+$",
        r"^job\.status$",
        r"^(always|success|failure|cancelled)\(\)$",
        # A literal default for a var, e.g. `vars.X || 'us-west-2'`.
        r"^'[^']*'$",
    )
]

# A comparison against a literal or another safe field, permitted only under `if:`, where
# the result is a boolean the runner consumes rather than a string a shell sees.
# `head.repo.full_name` is fork-controlled, which is exactly why it must never reach a
# `run:` body, but comparing it is how the two trigger arms partition.
COMPARISON = re.compile(r"^[A-Za-z0-9_.'\"\[\]\-]+(==|!=)[A-Za-z0-9_.'\"\[\]\-]+$")

EXPRESSION = re.compile(r"\$\{\{(.+?)\}\}", re.DOTALL)

# A `run:` body can fetch the pull request with no `uses:` at all, which the previous
# guard missed entirely. Invariant 1 is about contributor code reaching the runner, not
# about one action.
SELF_FETCH = re.compile(r"\b(gh\s+pr\s+checkout|git\s+clone|git\s+fetch|git\s+checkout)\b")

findings: list[str] = []


def operands(expression: str) -> list[str]:
    """Split a compound condition so each operand is judged separately.

    The real two-arm `if:` is four operands joined by boolean operators, so requiring the
    whole condition to match one allowlist entry would reject it.
    """
    parts = re.split(r"&&|\|\|", expression)
    return [p.strip(" ()!\t\n") for p in parts if p.strip(" ()!\t\n")]


def check_expressions(text: str, where: str, *, allow_comparison: bool) -> None:
    for raw in EXPRESSION.findall(str(text)):
        for operand in operands(raw.strip()):
            if any(a.match(operand) for a in ALLOWED_EXPRESSIONS):
                continue
            if allow_comparison and COMPARISON.match(operand.replace(" ", "")):
                continue
            findings.append(
                f"{where}: expression not allowlisted: ${{{{ {operand} }}}}. "
                "Add it to ALLOWED_EXPRESSIONS only if it cannot carry "
                "contributor-controlled text."
            )


def walk(node: object, path: str, in_if: bool) -> None:
    """Walk the parsed tree. Text position is not meaningful; structure is."""
    if node is None:
        return

    if isinstance(node, (str, int, float, bool)):
        check_expressions(node, path or "<root>", allow_comparison=in_if)
        return

    if isinstance(node, list):
        for i, item in enumerate(node):
            walk(item, f"{path}[{i}]", in_if)
        return

    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)

            if key == "uses" and isinstance(value, str):
                action = value.strip()
                if action not in ALLOWED_USES:
                    findings.append(
                        f"{here}: uses `{action}`, which is not allowlisted. A credentialed "
                        "job must not run an action that could fetch contributor code, and a "
                        "local action (`./...`) is contributor-authored on the fork arm."
                    )
                continue

            if key == "run" and isinstance(value, str):
                hit = SELF_FETCH.search(value)
                if hit:
                    findings.append(
                        f"{here}: the shell fetches the pull request (`{hit.group(0)}`). "
                        "Contributor code must never enter this runner; the runtime reads "
                        "the diff through the API."
                    )

            walk(value, here, True if key == "if" else in_if)


def load(path: str) -> dict | None:
    """Parse a workflow, refusing to report success on anything unusable.

    The previous guard printed "invariants hold" for an unreadable file, and for three
    bytes of garbage that a `null` API response base64-decoded into. Every failure here
    is fatal rather than skipped.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        print(f"::error::{path}: cannot be read ({error}); refusing to report success.", file=sys.stderr)
        return None

    if not text.strip():
        print(f"::error::{path}: empty; refusing to report success.", file=sys.stderr)
        return None

    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as error:
        first = str(error).splitlines()[0]
        print(f"::error::{path}: not valid YAML ({first}); refusing to report success.", file=sys.stderr)
        return None

    if not isinstance(doc, dict):
        print(f"::error::{path}: not a YAML mapping; refusing to report success.", file=sys.stderr)
        return None

    # A sentinel. If what was fetched has no jobs, it is not the reviewer workflow, so
    # something went wrong with the fetch rather than with the file's contents.
    if not isinstance(doc.get("jobs"), dict) or not doc["jobs"]:
        print(f"::error::{path}: no `jobs` mapping; this is not the reviewer workflow.", file=sys.stderr)
        return None

    return doc


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: reviewer_guard.py <workflow.yml> [...]", file=sys.stderr)
        return 2

    for path in argv:
        doc = load(path)
        if doc is None:
            return 1
        walk(doc, "", False)

    if findings:
        for f in findings:
            print(f"::error::{f}", file=sys.stderr)
        print(f"\n{len(findings)} violation(s) of the reviewer safety invariants.", file=sys.stderr)
        return 1

    print(
        f"Reviewer safety invariants hold across {len(argv)} file(s): every `uses:` is "
        "allowlisted, every `${{ }}` expression is allowlisted, and no shell fetches the "
        "pull request."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
