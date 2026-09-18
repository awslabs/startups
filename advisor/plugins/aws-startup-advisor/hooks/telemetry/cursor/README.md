# Cursor hook registration

`.cursor-plugin/plugin.json` points `hooks` at this directory's `hooks.json`, so Cursor
reads these registrations and never the sibling `hooks/hooks.json`, which is Claude
Code's (PascalCase events, `${CLAUDE_PLUGIN_ROOT}` substitution). Both files run the
same `emit.mjs`; only the registration differs.

Cursor reaches a plugin nested under `advisor/plugins/` through the marketplace manifest
beside it, `advisor/plugins/.cursor-plugin/marketplace.json`, which lists the plugin by
relative path (the same shape `migrate/plugins/` already uses). Installing the skills with
`npx skills add` delivers Markdown only, so a Cursor user installed that way gets no hooks
and no telemetry.

## Events

| Event           | Role                                                                                                |
| --------------- | --------------------------------------------------------------------------------------------------- |
| `afterFileEdit` | Fires for any agent edit; run in reconcile mode so the payload's path spelling cannot cost an event |
| `stop`          | End-of-turn reconcile, the same role as Claude Code's `Stop`                                        |
| `sessionEnd`    | Final sweep for this session's runs                                                                 |

## Host differences the emitter absorbs

|                   | Claude Code            | Cursor                                                 |
| ----------------- | ---------------------- | ------------------------------------------------------ |
| Session id        | `session_id`           | `conversation_id` on tool, file and stop hooks         |
| Working dir       | `cwd`                  | `workspace_roots[0]` on file hooks                     |
| Edited path       | `tool_input.file_path` | top-level `file_path`                                  |
| Reported `source` | `CLAUDE_CODE`          | `CURSOR`, from `CURSOR_VERSION` / `CURSOR_PROJECT_DIR` |

## Known limits

- Hook commands are written plugin-root-relative, following Cursor's plugin examples.
  Cursor does not document how plugin hook commands resolve; if nothing fires, this is
  the first thing to check.
- Cursor cloud agents run neither `sessionStart` nor `sessionEnd`, so there is no
  final sweep there.
- Cursor defines no per-plugin data directory, so `installId` lives in
  `~/.aws-startups-plugins`.
- Exit codes: `0` is success and `2` blocks. `emit.mjs` always exits `0`.
