---
name: hcls-stack-check
description: >-
  Reads an AWS account's resource inventory (a live AWS Resource Explorer pull,
  or a local export) and reports two
  facts per resource: whether its service is on AWS's published HIPAA Eligible
  Services Reference list, and whether it sits in an EU region / whether the
  service offers an EU region. Factual membership + region check only, NOT a
  compliance assessment and NOT legal advice. Use when someone asks about HIPAA
  eligibility, EU data residency, HCLS readiness, ghost instances, or "what is
  running in my account and where." Triggers: HIPAA eligible, HIPAA eligibility,
  EU data residency, EU region check, HCLS readiness, stack readiness, check my
  stack, ghost instances, what is running in my account, is my stack in the EU.
license: Apache-2.0
compatibility: "Kiro CLI, Claude Code, Quick Desktop"
metadata:
  author: alschmic
  last_validated: 2026-09-28
  risk_tier: L2
  audience: startup
---

# Skill: hcls-stack-check

## Overview

Produce a factual HCLS readiness snapshot of an AWS account's inventory. For
each resource discovered in the account's resource inventory (via AWS Resource
Explorer, or a local export), report:

1. **HIPAA eligibility**: is the resource's service on AWS's published HIPAA
   Eligible Services Reference list (yes / yes-with-caveat / not-on-list)?
2. **EU residency**: is the resource in an EU region, and does the service even
   offer an EU region (yes / no / unknown)?

This is a **factual membership + region check only. It is NOT a compliance
assessment and NOT legal advice.** It reports list membership and region facts,
never a "HIPAA-compliant" or "GDPR-ready" verdict.

**Why one skill, not two:** the HIPAA and EU checks share the same trigger
vocabulary ("HCLS readiness", "check my stack"), the same input (one topology),
and the same output (one table). They are one readiness question asked two ways,
so they are consolidated per the >70%-shared-trigger rule rather than split.

### When to use

Use when a startup SA references an account's resource inventory, HIPAA
eligibility, EU
data residency, or healthcare/life-sciences readiness. For example: "which
resources run on non-HIPAA-eligible services?", "is everything in my account in
the EU?", "any ghost instances not deployed via IaC?".

### When NOT to use

- Do **not** produce a compliance verdict ("HIPAA-compliant", "GDPR-ready"),
  because this skill only checks list membership and region facts.
- Do **not** give legal advice.

## Responsible AI disclosure

This is an **assessment-support** skill. It surfaces published facts (list
membership, region) to inform a human's judgment; it does not make eligibility,
compliance, or legal determinations. A qualified human must interpret the
report. Every generated report carries the verbatim AWS HIPAA disclaimer and the
not-a-compliance boundary statement, and both MUST be shown to the user.

## Running the deterministic core

The skill base directory is given in the "Base directory for this skill: X" line
the harness emits at load time. Call it `<SKILL_BASE>`. The Python lives under:

- `$SCRIPTS` = `<SKILL_BASE>/scripts`

Run it with `uv` so the pinned dependencies (`boto3>=1.43`, which ships the
Resource Explorer `ListResources` paginator) are present. Do **not** run a bare
`python src/main.py`: there is no `src/`, and a relative path is resolved
against the user's working directory, not the skill:

```bash
uv run --project "$SCRIPTS" python "$SCRIPTS/main.py" [--topology <live|path>] \
    [--assume-role-arn <arn> [--external-id <id>]]
```

If `uv` is missing, tell the user to install it
(https://docs.astral.sh/uv/getting-started/installation/, e.g. `brew install uv`)
and stop.

## External references (inventory)

The skill reads these external sources at runtime. All access is read-only.

| Reference                                                                                                      | Purpose                                   | Access                                    |
| -------------------------------------------------------------------------------------------------------------- | ----------------------------------------- | ----------------------------------------- |
| AWS HIPAA Eligible Services Reference (`https://aws.amazon.com/compliance/hipaa-eligible-services-reference/`) | Source of truth for eligibility           | HTTPS GET, host-validated, live every run |
| AWS Resource Explorer (`resource-explorer-2`: ListResources, GetIndex)                                         | Enumerate resources (CFN + out-of-IaC)    | Read-only API                             |
| AWS SSM global-infrastructure public parameters (`ssm:GetParametersByPath`)                                    | Which regions a service offers            | Read-only, public params                  |
| AWS STS (`sts:AssumeRole`, optional)                                                                           | Assume a **user-named** role for the pull | Read-only, opt-in via `--assume-role-arn` |

**Why not the DevOps Agent account role:** that role trusts only
`aidevops.amazonaws.com` and carries confused-deputy conditions, so a plain
`sts:AssumeRole` with user credentials fails, and making it work would mean
loosening that trust policy. Instead, the live pull enumerates resources via
Resource Explorer under the **caller's own credentials** (default chain or
`AWS_PROFILE`), or a role the **user explicitly names** with `--assume-role-arn`.

**Risk tier L2 rationale (OWASP AST04):** the skill may perform a cross-account
`sts:AssumeRole` into a role the user names (never the agent role). Everything
downstream is strictly read-only (no writes, no mutations), and no credentials
are hardcoded (default chain, `AWS_PROFILE`, or the opt-in role). Because it can
assume a user-provided role, it is L2, not L1.

## The rules this skill enforces

These invariants are implemented in the deterministic core (`scripts/`) and
stated here so the behavior is auditable. Follow them; do not re-implement them
by hand.

- **Rule 1, fail closed on the topology source.** Live pull via Resource
  Explorer (caller credentials, or a user-named role) by default, or a local
  `.json` export. If the source is unreachable or misconfigured, stop with an
  actionable error. Never emit a partial inventory that could read as
  "all clear." Resource enumeration uses `ListResources` (paginated), never
  `Search` (which silently caps at 1,000 results).
- **Rule 2, HIPAA list is live-only and gated.** Fetch the reference page live
  every run (no cache, no bundled fallback). Trust the parse only if at least 50
  services parsed AND sentinels S3/EC2/RDS present; otherwise fail loudly. A
  dev-only local override (`HCLS_SNAPSHOT_FILE`) is labelled `dev-override`, not
  `live`.
- **Rule 3, membership matching is exact, caveat-aware, and honest about gaps.**
  Normalized, case-insensitive name match (strip a leading `Amazon` or `AWS`
  prefix; index parenthesized short codes). Verdicts: `yes` / `yes-with-caveat`
  / `not-on-list` / `unmapped`. A resource whose service code cannot be resolved
  to a known AWS name is shown as `unknown` with an `unmapped` verdict, never
  dropped, and never a false `not-on-list`.
- **Rule 4, region facts are tri-state; EU availability may be unknown.** EU
  classification is `yes` / `no` / `global` / `unknown`; a global or
  empty-region resource reads `global`/`unknown`, never a misleading `no`. A
  live SSM lookup reports whether the service even offers an EU region. (Note:
  `eu-west-2` London and `eu-central-2` Zurich are NOT EU regions.)
- **Rule 5, make coverage gaps visible.** Resource Explorer preflight to
  OK / HIGH / INFO. **OK requires an AGGREGATOR index** (all regions searched);
  a LOCAL-only index is INFO (one region only). The preflight is evaluated
  against the account the inventory came from; if it was checked in a different
  account, coverage is reported as unverified. If RE status can't be determined,
  report coverage as unverified, never a false all-clear.

## Workflow

Run the deterministic core; it wires source, ingest, HIPAA snapshot, preflight,
per-resource checks, and report in one pass.

### 1. Resolve and load the topology

- **Mode:** code
- **Tool:** `uv run --project "$SCRIPTS" python "$SCRIPTS/main.py" [--topology <live|path>] [--assume-role-arn <arn>]` (default: live)
- **Input:** optional `--topology` (a local `.json` export path, or `live`); optional `--assume-role-arn` / `--external-id`
- **Output:** normalized resources `{resource_id, service, region}` plus active discovery paths and the inventory's account id
- **Validate:** at least the source resolved without error; discovery paths recorded
- **On failure:** the run stops and prints an actionable message, e.g. "Could
  not enumerate resources via AWS Resource Explorer (no index). Enable Resource
  Explorer with an aggregator index, run with credentials for the right account,
  or run against a local export with `--topology <path>`." Do not proceed with a
  partial stack.

### 2. Fetch and validate the HIPAA list

- **Mode:** code
- **Tool:** `uv run --project "$SCRIPTS" python "$SCRIPTS/main.py"` (same run)
- **Input:** none (live fetch); optional dev override via `HCLS_SNAPSHOT_FILE`
- **Output:** validated list of `{name, caveat}` services
- **Validate:** at least 50 services AND S3/EC2/RDS present (the gate)
- **On failure:** stop and report "Could not retrieve/validate the live HIPAA
  Eligible Services list; not reporting against a partial list." Never fall back
  to stale or empty data.

### 3. Check each resource and render the report

- **Mode:** code
- **Tool:** `uv run --project "$SCRIPTS" python "$SCRIPTS/main.py"` (same run)
- **Input:** normalized resources plus validated HIPAA list plus RE preflight status
- **Output:** the markdown report (see Output)
- **Validate:** every resource has a HIPAA verdict and an EU value; coverage
  badge present; disclaimer and boundary present
- **On failure:** if no resources resolved, still render the report with a
  "(no resources with a resolvable service)" row and the coverage note, so the
  empty state is a reported state, not a crash.

## Output

A single markdown report, in this order:

1. Title
2. **AWS HIPAA disclaimer (verbatim)**, required
3. **Not-a-compliance boundary statement**, required
4. HIPAA list source line (`live, fetched <ts>` or `dev-override`, service count)
5. Discovery-coverage badge: 🟢 OK / 🟡 INFO / 🔴 HIGH (color paired with the
   text label, so it is never color-only). OK requires an AGGREGATOR index.
6. Results table: `resource_id | service | hipaa_eligible | region | eu`
   (`hipaa_eligible` is `yes`, `yes* (<caveat>)`, `not on list`, or `unmapped`;
   `eu` is `yes` / `no` / `global` / `unknown`, optionally annotated with
   whether the service offers an EU region)
7. Footer: topology source (live vs local), the inventory's account id, and
   active discovery paths

**Display the report verbatim.** The orchestrator MUST surface the report text
as produced and MUST NOT summarize, re-rank, or re-interpret it, because
paraphrasing a factual eligibility/region report can reintroduce exactly the
compliance-verdict framing this skill forbids.

## Lessons Learned

### Do

- Keep deterministic work (parsing, matching, region/threshold logic) in code;
  the LLM is for framing and answering follow-up questions about the report.
- Fail closed and say what the user does next, in plain language.
- Preserve the multi-state outcomes (`yes-with-caveat`, `unmapped`, EU
  `global`/`unknown`, coverage `INFO`). They carry real information a binary
  would destroy.

### Don't

- Don't turn the report into a compliance verdict or legal advice.
- Don't cache or hardcode the HIPAA list; it must be live and gated every run.
- Don't report "all clear" when coverage is unverified (RE status unknown, a
  LOCAL-only index, or the wrong account was checked).
- Don't assume the DevOps Agent account role; use caller credentials or a
  user-named role.

### Common failures

- **No Resource Explorer index** in the target account blocks the live pull.
  Fix: enable Resource Explorer with an aggregator index, or use
  `--topology <path>`.
- **Only a LOCAL Resource Explorer index** (no aggregator) searches one region
  only, so coverage is INFO, not OK. Fix: create an aggregator index.
- **Preflight checked the wrong account** (your shell profile differs from the
  inventory's account) downgrades coverage to unverified. Fix: run with
  credentials for the inventory's account.
- **HIPAA page layout change** trips the validation gate and the run stops (by
  design) rather than under-reporting.

### When to ask the user

- When neither a live pull nor a local export path is available, ask which the
  user wants rather than guessing.
- When a named role (`--assume-role-arn`) or the account scope is ambiguous,
  confirm scope if the enumerated inventory looks unexpectedly large or empty.

## Runtime notes

- AWS calls use the default boto3 credential chain, or `AWS_PROFILE` if set, or
  an opt-in user-named role via `--assume-role-arn`. Nothing is hardcoded. All
  downstream use is read-only.
- For offline/dev runs, an opt-in local HIPAA snapshot via `HCLS_SNAPSHOT_FILE`
  is validated through the same gate and labelled `dev-override`. No data ships
  in the repo.

## Evaluation cases

1. **Happy path (local export):** `--topology scripts/fixtures/sample_topology.json`
   renders a report with a HIPAA verdict and EU value for every resolvable
   resource, disclaimer and boundary present. Expected: exit 0.
2. **Caveat match:** a resource on a service listed with a caveat produces a row
   showing `yes* (<caveat>)`, not a bare `yes`.
3. **Unmapped service:** a resource whose service code is not in the resolver
   map (e.g. an exotic type) shows `unknown (<raw>)` with an `unmapped` verdict,
   not a dropped row or a false `not on list`.
4. **Fail-closed source:** live pull with no Resource Explorer index raises
   `TopologySourceError`, an actionable message, and a non-zero exit, with no
   partial report emitted.
5. **Coverage gap (edge):** topology with only CloudFormation discovery and RE
   disabled includes the 🔴 HIGH coverage warning; a LOCAL-only index yields
   🟡 INFO (not OK).
6. **HIPAA gate failure (edge):** a too-small/garbled list (see
   `scripts/fixtures/hipaa_page_too_small.html`) stops the run with a validation
   error rather than reporting against a partial list.
