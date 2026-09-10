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

Usage: tools/reviewer-guard/reviewer_guard.py <workflow.yml> [...]
Exit 0 when every file satisfies the invariants, 1 on a violation or an unusable file,
2 on a usage error.
"""

from __future__ import annotations

import re
import sys

import hashlib

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

class StrictLoader(yaml.SafeLoader):
    """Rejects duplicate mapping keys.

    `safe_load` keeps the last of a duplicated key, so a step could carry both
    `uses: actions/checkout@v4` and an allowlisted `uses:` and the guard would examine
    only the second. A control that provably ignores bytes present in the file must fail
    rather than guess which parser wins.
    """


def _no_duplicate_keys(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.YAMLError(
                f"duplicate key {key!r} at line {key_node.start_mark.line + 1}"
            )
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)

# Shell bodies the credentialed job may run, pinned by sha256 of the normalised text.
#
# This replaced a four-pattern search for `git clone|git fetch|git checkout|gh pr
# checkout`, which was the one denylist left inside an allowlist guard and was doing the
# load-bearing work for invariant 1. Adversarial review missed ten of twelve fetch
# spellings against it. Two needed no cleverness at all: `git -c protocol.version=2 fetch`
# and `git -C . checkout` defeat `\bgit\s+fetch\b` purely because the words are not
# adjacent, and a backslash-newline between `git` and `clone` defeats `\s+`. The headline
# bypass was a twelve-line step that reads as an ordinary caching optimisation:
#
#     gh api "repos/${GITHUB_REPOSITORY}/tarball/${HEAD_SHA}" > contribution.tgz
#     tar xzf contribution.tgz -C contribution --strip-components=1
#     make -C contribution/solution-architecture prepare
#
# No `uses:`, no matched pattern, contributor code executing with credentials.
#
# Pinning by hash is the only form that closes that class, and it closes invariant 2's
# non-expression channel at the same time: `$GITHUB_HEAD_REF` and `$GITHUB_EVENT_PATH`
# hand fork-controlled text to a shell with no `${{ }}` anywhere, so no expression
# allowlist can see them.
#
# The cost is deliberate. Any edit to a shell body fails until the hash is updated, and
# that hash change is the review artifact. Regenerate with:
#     python3 .github/workflows/tools/reviewer_guard.py --hashes <workflow.yml>
ALLOWED_RUN_SHA256 = {
    "1d556cc9a31779bafb63600b5129316af0dc0d988486898052f66700b0366717": "Signal review started",
    "8bc2bf945242477da317013e698de9698d16a1ffa5205be70661e0e675a96b8b": "Check configuration",
    "4dcb13dcf74779237af1e7f4c2b1cac3f05d35e823bc48e50c617dd9b69a9cfd": "Invoke reviewer",
    "944f7318c9a42c5060b8319c042a237d09cda40ecf96c5513f245e8578804294": "Summarize the review",
    "81ab29eb4c6b17f33dc1087fc1dff4e432b62ef674a3b6ea6ece7753b05afc08": "Signal review finished",
}

# Keys permitted at job and step level. `container:`, `services:`, and
# `defaults.run.shell` all execute code and the guard previously had no concept of any of
# them: a one-line `container:` with a hostile `--entrypoint` passed clean. Enumerating
# permitted keys closes those and whatever GitHub adds next.
ALLOWED_JOB_KEYS = {
    "name", "if", "needs", "permissions", "runs-on", "timeout-minutes", "env",
    "concurrency", "steps", "outputs",
}
ALLOWED_STEP_KEYS = {"name", "id", "if", "uses", "with", "env", "run", "working-directory"}


def normalise_run(body: str) -> str:
    """Trailing whitespace and surrounding blank lines are not semantic."""
    return "\n".join(line.rstrip() for line in body.strip().splitlines())


findings: list[str] = []


def operands(expression: str) -> list[str]:
    """Split a compound condition so each operand is judged separately.

    The real two-arm `if:` is four operands joined by boolean operators, so requiring the
    whole condition to match one allowlist entry would reject it.
    """
    parts = re.split(r"&&|\|\|", expression)
    out = []
    for part in parts:
        # Parentheses are stripped only when they wrap the whole operand, so `always()`
        # survives as `always()` rather than becoming an unmatchable `always`.
        part = part.strip(" !\t\n")
        while part.startswith("(") and part.endswith(")") and part.count("(") == part.count(")"):
            part = part[1:-1].strip(" !\t\n")
        if part:
            out.append(part)
    return out


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

            # A non-string `uses:` or `run:` was silently skipped, so `uses:
            # ["actions/checkout@v4"]` and a list-valued `run:` passed clean. In a guard
            # whose premise is that anything unrecognised fails, an unexpected type is a
            # finding rather than a reason to stop looking.
            if key in ("uses", "run") and not isinstance(value, str):
                findings.append(
                    f"{here}: `{key}` is {type(value).__name__} rather than a string; "
                    "refusing to interpret it."
                )
                continue

            if key == "uses":
                action = value.strip()
                if action not in ALLOWED_USES:
                    findings.append(
                        f"{here}: uses `{action}`, which is not allowlisted. A credentialed "
                        "job must not run an action that could fetch contributor code, and a "
                        "local action (`./...`) is contributor-authored on the fork arm."
                    )
                continue

            if key == "run":
                digest = hashlib.sha256(normalise_run(value).encode()).hexdigest()
                if digest not in ALLOWED_RUN_SHA256:
                    findings.append(
                        f"{here}: shell body is not allowlisted (sha256 {digest}). Every "
                        "script this credentialed job runs is pinned, because a denylist of "
                        "fetch commands missed ten of twelve spellings and could not see "
                        "fork data arriving through $GITHUB_HEAD_REF or $GITHUB_EVENT_PATH "
                        "at all. If this change is intended, add the hash with "
                        "`reviewer_guard.py --hashes` and let the hash change be reviewed."
                    )
                continue

            # `if:` is a scalar in GitHub's schema. Checking it directly, rather than
            # propagating a flag down the subtree, stops a nested `run:` from inheriting
            # permission to contain a comparison against a fork-controlled field.
            if key == "if" and isinstance(value, str):
                check_expressions(value, here, allow_comparison=True)
                continue

            walk(value, here, in_if)


def check_structure(doc: dict, path: str) -> None:
    """Keys and settings the guard requires, rather than merely tolerates.

    Everything above answers "was something bad added". These answer "was something
    load-bearing removed", which the guard previously did not ask at all: deleting the
    `paths:` filter and the two-arm `if:` partition, and setting `permissions: write-all`,
    all passed clean.
    """
    triggers = doc.get(True, doc.get("on"))
    if not isinstance(triggers, dict) or "pull_request_target" not in triggers:
        return  # not a credentialed fork-arm workflow; nothing here applies

    ptt = triggers.get("pull_request_target") or {}
    if not isinstance(ptt, dict) or not ptt.get("paths"):
        findings.append(
            f"{path}: `pull_request_target` has no `paths:` filter, so every pull request "
            "in the repository would start a credentialed run."
        )

    for job_id, job in doc["jobs"].items():
        if not isinstance(job, dict):
            findings.append(f"{path}: job `{job_id}` is not a mapping.")
            continue
        where = f"{path}: jobs.{job_id}"

        for key in job:
            if key not in ALLOWED_JOB_KEYS:
                findings.append(
                    f"{where}.{key}: job key not allowlisted. `container:`, `services:`, and "
                    "`defaults.run.shell` all execute code, so unknown keys fail closed."
                )

        for i, step in enumerate(job.get("steps") or []):
            if not isinstance(step, dict):
                findings.append(f"{where}.steps[{i}]: not a mapping.")
                continue
            for key in step:
                if key not in ALLOWED_STEP_KEYS:
                    findings.append(f"{where}.steps[{i}].{key}: step key not allowlisted.")

        perms = job.get("permissions")
        if not isinstance(perms, dict):
            findings.append(
                f"{where}.permissions: must be an explicit mapping. `write-all`, or "
                "inheriting the default, gives a credentialed fork run far more than it needs."
            )
        else:
            for scope, level in perms.items():
                if scope not in ("id-token", "statuses") and level != "none":
                    findings.append(
                        f"{where}.permissions.{scope}: `{level}` is more than this job needs. "
                        "Only `id-token` and `statuses` are permitted; the runtime posts its "
                        "review with its own App token."
                    )

        condition = str(job.get("if") or "")
        if "head.repo.full_name" not in condition:
            findings.append(
                f"{where}.if: does not partition on `head.repo.full_name`. Without it the two "
                "trigger arms overlap and a same-repo push is reviewed twice, or a fork run "
                "takes the arm meant for same-repo branches."
            )


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
        # B506 is suppressed below, and the reason matters: StrictLoader subclasses
        # SafeLoader and only adds duplicate-key rejection, so it constructs plain types
        # and no arbitrary objects. `safe_load` cannot be used because it accepts no
        # Loader, and dropping the loader would restore the duplicate-key bypass this
        # exists to close. Keep the annotation bare: bandit reads anything after `nosec`
        # as a list of test ids, so prose on that line becomes invented test names.
        doc = yaml.load(text, Loader=StrictLoader)  # nosec B506
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


def print_hashes(paths: list[str]) -> int:
    for path in paths:
        doc = load(path)
        if doc is None:
            return 1
        for job_id, job in doc["jobs"].items():
            for i, step in enumerate(job.get("steps") or []):
                body = step.get("run") if isinstance(step, dict) else None
                if isinstance(body, str):
                    digest = hashlib.sha256(normalise_run(body).encode()).hexdigest()
                    name = step.get("name", f"jobs.{job_id}.steps[{i}]")
                    print(f'    "{digest}": "{name}",')
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--hashes":
        return print_hashes(argv[1:])
    if not argv:
        print("usage: reviewer_guard.py <workflow.yml> [...]", file=sys.stderr)
        return 2

    for path in argv:
        doc = load(path)
        if doc is None:
            return 1
        walk(doc, "", False)
        check_structure(doc, path)

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
