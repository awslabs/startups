# Migration telemetry

This protocol applies to migration runs under `.migration/` owned by
`GCP_TO_AWS`, `HEROKU_TO_AWS`, or `LLM_TO_BEDROCK`. A skill with its own run root,
such as `.agent-advisor/`, does not invoke this protocol.

## Choose the reporting path

Use the identity of the agent running this skill:

- **Claude Code or Cursor:** do not invoke the reporting command below. Use the
  existing host hooks, including when a skill was installed through skills.sh.
  Do not switch to CLI because hooks appear missing, delayed, or unsuccessful.
- **Every other agent:** invoke the reporting command at the boundaries below.
  Do not wait for hooks or use snapshot timestamps to choose the reporting path.

This restriction is for reporting only. The existing consent commands
(`consent get`, `consent grant`, `consent revoke`) remain available on every host.
Follow the migration initialization consent step; do not grant consent implicitly.
The emitter also rejects CLI reporting when it recognizes a Claude Code or Cursor
environment. Do not unset host environment variables to bypass that check.

## Locate the emitter

Set `$SKILL_ROOT` to the absolute directory containing the current skill's
`SKILL.md`, and `$REPO` to the absolute project root that contains `.migration/`.
Set `$EMIT` to `$SKILL_ROOT/references/vendored/telemetry/emit.mjs`. Use this
bundled file for consent and reporting; it does not require sibling skills or
a plugin installation. If the file or Node.js is unavailable, skip telemetry
and continue the migration.

These paths are not environment variables supplied by the host. Resolve them
from the loaded skill and project, then use absolute paths in each tool call or
assign and use the variables within the same shell invocation. Do not rely on
shell variables surviving between tool calls.

## Report after state is on disk

On other agents, run this command from the main workflow, not from a dispatched
worker that produces phase artifacts:

```bash
(cd "$REPO" && node "$EMIT" --reconcile --via cli </dev/null)
```

Invoke it:

1. After initialization has recorded consent and written `.phase-status.json`.
2. After each phase-status update, including skipped phases, sidebar decisions,
   and `current_phase: complete` for a decision-only or executed run.
3. After writing `.gate-failures.json`, before returning a gate failure to the user.
4. On resume, after selecting and validating the existing run, before continuing.
   Keep its existing `run_id`.
5. For llm-to-bedrock, after creating or resuming its own `.bedrock-*` run and
   after recording its completion.

The emitter reads state and artifacts itself. Do not construct a payload, invent
attributes or session identifiers, or edit `.telemetry-snapshot.json`. Repeated
calls reconcile the same snapshot and skip already processed transitions.
Telemetry failure must not block phase work, change its result, or cause retries
of the migration itself.
