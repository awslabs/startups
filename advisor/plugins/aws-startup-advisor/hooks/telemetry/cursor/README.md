# Cursor hook registration

`.cursor-plugin/plugin.json` points `hooks` at this directory's `hooks.json`, so Cursor
reads these registrations and never the sibling `hooks/hooks.json`, which is Claude
Code's (PascalCase events, `${CLAUDE_PLUGIN_ROOT}` substitution). Both files run the
same `emit.mjs`; only the registration differs.

Hook commands reference the script through `${CURSOR_PLUGIN_ROOT}`, the form every plugin
in Cursor's own [plugins repository](https://github.com/cursor/plugins) uses; a
plugin-root-relative path such as `./hooks/...` is not documented to resolve.

Cursor reaches a plugin nested under `advisor/plugins/` only through a marketplace
manifest at the repository root, `.cursor-plugin/marketplace.json`, which lists the plugin
by relative path; that is the layout Cursor's own multi-plugin repository documents.
Installing the skills with `npx skills add` delivers Markdown only, so a Cursor user
installed that way gets no hooks and no telemetry.

## Installing locally to test

Cursor loads local plugins from `~/.cursor/plugins/local/`. Copy the plugin directory
there; a symlink whose target lives elsewhere on disk is skipped.

```bash
mkdir -p ~/.cursor/plugins/local
cp -R advisor/plugins/aws-startup-advisor ~/.cursor/plugins/local/aws-startup-advisor
```

Then run **Developer: Reload Window** and check **Customize** for the plugin's skills and
three hooks. Two conditions: local plugin imports must be allowed (an Enterprise setting
under Dashboard → Settings → Security & Identity → Marketplace and Plugins, off by
default), and a marketplace plugin of the same name, if installed, takes precedence over
the local copy, so uninstall it first.

Launch Cursor from a terminal when pointing the emitter at a test endpoint: a GUI-launched
Cursor does not inherit the shell's `AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT`, and the
compiled default is production.

## Events

| Event           | Role                                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------------- |
| `afterFileEdit` | Fires after the agent edits a file; run in reconcile mode so the payload's path spelling cannot cost an event |
| `stop`          | End-of-turn reconcile, the same role as Claude Code's `Stop`                                                  |
| `sessionEnd`    | Final sweep for this session's runs                                                                           |

`afterFileEdit` is documented for the agent's edit tool. Whether a state file written from
a shell command also fires it is not documented; the `stop` reconcile re-reads the state
file regardless of writer, so such a transition is reported at the end of the turn instead.

## Host differences the emitter absorbs

|                   | Claude Code            | Cursor                                                 |
| ----------------- | ---------------------- | ------------------------------------------------------ |
| Session id        | `session_id`           | `conversation_id` on tool, file and stop hooks         |
| Working dir       | `cwd`                  | `workspace_roots[0]` on file hooks                     |
| Edited path       | `tool_input.file_path` | top-level `file_path`                                  |
| Reported `source` | `CLAUDE_CODE`          | `CURSOR`, from `CURSOR_VERSION` / `CURSOR_PROJECT_DIR` |

## Known limits

- Cursor cloud agents run neither `sessionStart` nor `sessionEnd`, so there is no
  final sweep there.
- Cursor defines no per-plugin data directory, so `installId` lives in
  `~/.aws-startups-plugins`.
- Exit codes: `0` is success and `2` blocks. `emit.mjs` always exits `0`.
