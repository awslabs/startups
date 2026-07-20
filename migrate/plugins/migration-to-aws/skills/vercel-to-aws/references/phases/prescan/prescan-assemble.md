---
_assemble: prescan-assemble
_of_phase: prescan
_reads:
  - tier1-collect (repo_access, next_build_health, vercel_token_present, project_list)
  - build-free-scan (next_version, package_manager, has_sharp_dependency, lockfile_census, has_middleware, has_vercel_json)
_produces:
  - tier1-signals.json
  - assessment-state.json
---

# PreScan Phase: Assembler

> Combines the `tier1-collect` and `build-free-scan` fragment contributions into
> `tier1-signals.json`, seeds `assessment-state.json.inputs_received.tier1`, and
> runs the phase's completion gate. This is the SINGLE creator of
> `tier1-signals.json` — the fragments themselves never write it directly.

**Execute ALL steps in order. Do not skip or deviate.**

---

## Step 1: Merge Fragment Contributions

Combine both fragments' contributions into one object:

```json
{
  "phase": "prescan",
  "timestamp": "<ISO 8601>",
  "repo_access": true,
  "next_build_health": "clean" | "failed" | "unattempted",
  "next_build_failure_summary": "<short summary, only if failed>",
  "vercel_token_present": true,
  "project_list": ["<project-name>", ...],
  "project_scoping_needed": false,
  "next_version": "16.2.0",
  "package_manager": "pnpm@9.0.0",
  "has_sharp_dependency": false,
  "lockfile_census": ["pnpm-lock.yaml"],
  "has_middleware": true,
  "has_vercel_json": true
}
```

If either fragment recorded a `null`/missing value for any field, carry the
`null` through rather than fabricating a value — per SKILL.md's "do not fabricate
or infer data" constraint.

---

## Step 2: Write `tier1-signals.json`

Write the merged object to `$MIGRATION_DIR/tier1-signals.json`.

---

## Step 3: Seed `assessment-state.json`

Read the current `assessment-state.json` from `$MIGRATION_DIR` (written by
`prescan.md` Step 0's `_init` setup). Update it with a read-merge-write (never a
blind overwrite):

1. For each Tier 1 input (`repo_access`, `vercel_api_token`, `project_scope`),
   set `inputs_received.tier1.<input>.received` per what Step 1 found, and
   `received_at` to the current timestamp if newly received (leave unchanged if
   already `received: true` from a prior run — this is the first phase, so on a
   truly fresh run all Tier 1 entries are newly received).
2. If Step 4 of `prescan-collect.md` opportunistically detected any Tier 2/3
   inputs already present, seed those into `inputs_received.tier2`/`tier3` now
   too.
3. Update `last_updated` to the current timestamp.
4. Write the full file back.

Do not touch `findings`, `clarify_answers`, or `report_history` here — those
remain the empty structures `prescan.md` Step 0 initialized (or, on a warm
re-entry, whatever they already were) until `discover`/`clarify`/`report`
populate them.

---

## Step 4: Determine `has_middleware` Downstream Signal

Confirm `tier1-signals.json.has_middleware` is set correctly — this single field
is what `clarify-ask.md` (Requirement 2.3) and the report's `appendix-m1`
conditional (Requirement 9.4) both key off of. Double-check it was not
accidentally left `null` when `build-free-scan` actually ran successfully.

---

## Completion Gate

Re-read `tier1-signals.json` and `assessment-state.json` from disk (never trust
in-memory state), then run the checks declared in `prescan.md`'s
`_postconditions`:

1. Both files exist.
2. Both parse as valid JSON.
3. `tier1-signals.json` has `next_version`, `package_manager`, `has_middleware`,
   `has_vercel_json`, and `project_list` populated (or explicitly `null` with a
   reason field alongside it).
4. `assessment-state.json` validates against
   `references/state/assessment-state.schema.json`, and
   `inputs_received.tier1` reflects what `prescan-collect.md` actually found
   (spot check: if `repo_access` was `true` in `tier1-signals.json`, then
   `inputs_received.tier1.repo_access.received` must also be `true`).

**On any failure:** emit exactly:

```
GATE_FAIL | phase=prescan | field=<failing file/field> | reason=<missing|invalid>
```

Do NOT modify artifacts to force a pass. Do NOT update `.phase-status.json`. Tell
the founder which input is missing or invalid.

**On all-pass:** emit exactly:

```
HANDOFF_OK | phase=prescan | artifacts=tier1-signals.json,assessment-state.json
```

Then update `.phase-status.json` per the read-merge-write protocol
(`INTERPRETER.md` § Phase-status update protocol): mark `phases.prescan`
`"completed"`, set `current_phase` to `discover`, update `last_updated` — in the
same turn as the phase's final output message (see `prescan.md` Step 4).

---

## Scope Boundary

**This assembler covers merging PreScan's two fragments and the completion gate
ONLY.**

FORBIDDEN — Do NOT include ANY of:

- Re-running any of the fragments' own detection logic
- Fabricating a value for a field neither fragment produced
- Advancing `.phase-status.json` before `HANDOFF_OK` is emitted

**Your ONLY job: merge, write, gate, hand off.**
