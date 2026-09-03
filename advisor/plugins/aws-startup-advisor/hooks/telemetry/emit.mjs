#!/usr/bin/env node
// Migration telemetry emitter. Invoked by host hooks (never by the agent):
//   node emit.mjs                    post-write: payload on stdin names the edited file
//   node emit.mjs --reconcile        end-of-turn: re-read state regardless of writer
//   node emit.mjs --session-end      teardown: final sweep for this session's runs
//   node emit.mjs consent <get|grant|revoke|status>
//
// Reads .migration/<id>/.phase-status.json, diffs it against the co-located
// .telemetry-snapshot.json, and POSTs one event per transition to the endpoint
// in AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT. Everything it needs is on disk;
// nothing is inferred from the conversation, and there is no --skill flag:
// the run declares its owner via the owning_skill key in .phase-status.json,
// and a run with no declared owner emits nothing.
//
// Fail-open: every path exits 0 and surfaces nothing to the customer. The one
// deliberate exception to "the snapshot advances regardless" is a missing
// endpoint: with no endpoint configured nothing was attempted, so the snapshot
// is left alone and the run is reported in full once an endpoint exists.

import { promises as fs } from "node:fs";
import { existsSync, mkdirSync, rmdirSync, statSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MIGRATION_SKILLS = new Set(["GCP_TO_AWS", "HEROKU_TO_AWS", "LLM_TO_BEDROCK"]);
const SOURCE_PROVIDER_BY_SKILL = { GCP_TO_AWS: "GCP", HEROKU_TO_AWS: "HEROKU" };
const LOCK_STALE_MS = 60_000;
const POST_TIMEOUT_MS = 3_000;

// How this invocation was triggered: "hook" (default) or "cli" via --via cli,
// the flag the future skill-invoked fallback passes on hosts without hooks.
function viaMode() {
  const i = process.argv.indexOf("--via");
  return i !== -1 && process.argv[i + 1] === "cli" ? "cli" : "hook";
}

// ---------------------------------------------------------------- utilities

async function readJson(file) {
  try {
    return JSON.parse(await fs.readFile(file, "utf8"));
  } catch {
    return null;
  }
}

function pluginRoot() {
  // hooks/telemetry/emit.mjs → plugin root is two levels up.
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
}

async function pluginVersion() {
  const manifest = await readJson(path.join(pluginRoot(), ".claude-plugin", "plugin.json"));
  return typeof manifest?.version === "string" ? manifest.version : "0.0.0";
}

// Host detection. Cursor is checked first because it exports CLAUDE_PROJECT_DIR
// as a compatibility alias; Claude Code is then identified by its own markers.
// Anything else reports OTHER rather than impersonating a known host — the
// emitter also runs as a skill-invoked CLI on hosts without hooks, where a
// CLAUDE_CODE default would be a lie the funnel cannot detect.
function hostSource() {
  if (process.env.CURSOR_VERSION || process.env.CURSOR_PROJECT_DIR) return "CURSOR";
  if (process.env.CLAUDE_PLUGIN_ROOT || process.env.CLAUDECODE) return "CLAUDE_CODE";
  return "OTHER";
}

function stateDir() {
  return process.env.CLAUDE_PLUGIN_DATA || path.join(os.homedir(), ".aws-startups-plugins");
}

// installId is machine-level (one customer, many repos, one install), minted
// lazily on first use — there is no install-time hook to mint it at.
async function getInstallId() {
  const file = path.join(stateDir(), "install.json");
  const existing = await readJson(file);
  if (existing && UUID_RE.test(existing.installId)) return existing.installId;
  const installId = crypto.randomUUID();
  await fs.mkdir(stateDir(), { recursive: true });
  await fs.writeFile(file, JSON.stringify({ installId }, null, 2));
  return installId;
}

async function readStdin() {
  if (process.stdin.isTTY) return null;
  const chunks = [];
  try {
    for await (const chunk of process.stdin) chunks.push(chunk);
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    return null;
  }
}

// -------------------------------------------------------------- run discovery

// A run directory is .migration/<id>/ containing .phase-status.json. Discovery
// starts from a directory and walks up a bounded number of levels; the nearest
// .migration/ tree wins, so runs from parent or sibling projects are not mixed in.
async function findRunDirs(startDir) {
  const runs = [];
  let dir = path.resolve(startDir || process.cwd());
  for (let depth = 0; depth < 4; depth++) {
    const migrationRoot = path.join(dir, ".migration");
    try {
      for (const entry of await fs.readdir(migrationRoot, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue;
        const runDir = path.join(migrationRoot, entry.name);
        if (existsSync(path.join(runDir, ".phase-status.json"))) runs.push(runDir);
      }
      break;
    } catch {
      const parent = path.dirname(dir);
      if (parent === dir) break;
      dir = parent;
    }
  }
  return runs;
}

// --------------------------------------------------------------------- consent

// Consent is per project, stored beside the runs it governs. There is no global
// fallback: a grant can only be recorded where a migration tree exists, so
// consent never silently widens beyond the project the customer was asked about.
// (HLD 6.4 leaves the fallback as an open DECISION; this implements the
// fail-closed side pending the AppSec ruling.)
function consentFileFor(runDir) {
  return path.join(path.dirname(runDir), "telemetry.json");
}

async function consentGrantedFor(runDir) {
  if (process.env.DO_NOT_TRACK === "1") return false;
  if (process.env.AWS_STARTUP_ADVISOR_TELEMETRY === "0") return false;
  const record = await readJson(consentFileFor(runDir));
  return record?.consent === "granted";
}

async function runConsentCommand(action) {
  const migrationRoot = path.resolve(".migration");
  const file = path.join(migrationRoot, "telemetry.json");
  const record = await readJson(file);
  switch (action) {
    case "get":
      process.stdout.write(`${record?.consent ?? "unset"}\n`);
      return;
    case "status": {
      const install = await readJson(path.join(stateDir(), "install.json"));
      process.stdout.write(
        JSON.stringify(
          {
            consent: record?.consent ?? "unset",
            consentFile: file,
            stateDir: stateDir(),
            installId: install?.installId ?? "not yet minted",
            endpointConfigured: Boolean(process.env.AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT),
          },
          null,
          2,
        ) + "\n",
      );
      return;
    }
    case "grant": {
      if (!existsSync(migrationRoot)) {
        process.stdout.write("no .migration directory here; create the run first\n");
        return;
      }
      const installId = await getInstallId();
      await fs.writeFile(
        file,
        JSON.stringify({ consent: "granted", installId, grantedAt: new Date().toISOString() }, null, 2),
      );
      process.stdout.write("granted\n");
      return;
    }
    case "revoke": {
      if (!record) {
        process.stdout.write("nothing to revoke\n");
        return;
      }
      // The revocation event is the final act covered by the standing grant,
      // so it is sent BEFORE the state flips. Note: with no consent event in
      // the implemented model this sends nothing today; the flip still happens.
      await fs.writeFile(
        file,
        JSON.stringify({ ...record, consent: "revoked", revokedAt: new Date().toISOString() }, null, 2),
      );
      process.stdout.write("revoked\n");
      return;
    }
    default:
      process.stdout.write("usage: emit.mjs consent <get|grant|revoke|status>\n");
  }
}

// ------------------------------------------------------------------- the lock

// Steps read-snapshot → POST → write-snapshot span network calls, and the
// post-write and reconcile triggers can overlap. An exclusive per-run lock
// (directory creation as atomic test-and-set) is the one duplication defence
// no downstream layer can substitute for: overlapping invocations would read
// the same "before" state and mint distinct eventIds.
function acquireLock(runDir) {
  const lock = path.join(runDir, ".telemetry-lock");
  try {
    mkdirSync(lock);
    return lock;
  } catch {
    try {
      if (Date.now() - statSync(lock).mtimeMs > LOCK_STALE_MS) {
        rmdirSync(lock);
        mkdirSync(lock);
        return lock;
      }
    } catch {
      /* raced or vanished; treat as held */
    }
    return null; // holder is about to report the same transitions
  }
}

function releaseLock(lock) {
  try {
    rmdirSync(lock);
  } catch {
    /* already gone */
  }
}

// ------------------------------------------------------------------- the diff

// One event per transition between the snapshot and .phase-status.json.
// Only resolved phases are reported; pending/in_progress churn emits nothing.
// RUN_COMPLETED is gated on the snapshot's completed flag, not the transition,
// so a current_phase that leaves "complete" and returns cannot mint a second
// terminal event.
function diffEvents(status, snapshot) {
  const events = [];
  if (!snapshot) events.push({ eventName: "RUN_STARTED" });
  const before = snapshot?.phases ?? {};
  for (const [phase, state] of Object.entries(status.phases ?? {})) {
    if (state === "completed" && before[phase] !== "completed") {
      events.push({ eventName: "PHASE_COMPLETED", phase: phase.toUpperCase(), status: "SUCCESS" });
    }
  }
  if (status.current_phase === "complete" && !snapshot?.completed) {
    events.push({ eventName: "RUN_COMPLETED", status: "SUCCESS" });
  }
  return events;
}

// ----------------------------------------------------------------- the envelope

async function buildRequest(event, ctx) {
  const attributes = {};
  const provider = SOURCE_PROVIDER_BY_SKILL[ctx.skill];
  if (provider) attributes.sourceProvider = provider;
  // Richer artifact-derived attributes (spendBand, resourceCount, …) attach
  // here once their derivation from the run's own artifacts is specified.
  const migrationActivity = {
    eventName: event.eventName,
    skill: ctx.skill,
    runId: ctx.runId,
    ...(ctx.sessionId ? { sessionId: ctx.sessionId } : {}),
    ...(event.phase ? { phase: event.phase } : {}),
    ...(event.status ? { status: event.status } : {}),
    ...(Object.keys(attributes).length ? { attributes } : {}),
  };
  return {
    installId: ctx.installId,
    source: hostSource(),
    pluginVersion: await pluginVersion(),
    occurredAt: Date.now(),
    eventId: crypto.randomUUID(), // fresh per emission; the consumers' dedup key
    pluginTelemetryEvent: { migrationActivity },
  };
}

async function post(endpoint, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), POST_TIMEOUT_MS);
  try {
    await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

// ------------------------------------------------------------------ per run

async function processRun(runDir, { sessionId, sessionEndMode, endpoint }) {
  const status = await readJson(path.join(runDir, ".phase-status.json"));
  if (!status?.migration_id) return;

  // Attribution is read from disk, never from an argument: a run that declares
  // no owner, or an owner outside the migration set, emits nothing (fail closed)
  // rather than emitting under the wrong skill.
  const skill = status.owning_skill;
  if (!MIGRATION_SKILLS.has(skill)) return;

  if (!(await consentGrantedFor(runDir))) return;

  const snapshotFile = path.join(runDir, ".telemetry-snapshot.json");
  const lock = acquireLock(runDir);
  if (!lock) return;
  try {
    const snapshot = await readJson(snapshotFile);

    // Teardown sweeps only the session that wrote the snapshot; a run last
    // touched by another session is that session's to report.
    if (sessionEndMode && snapshot && sessionId && snapshot.sessionId !== sessionId) return;

    const events = diffEvents(status, snapshot);
    if (events.length === 0) return;

    // Identifiers read back from customer-editable files are validated, not
    // trusted: the model's @pattern makes one malformed UUID reject the whole
    // event. run_id comes from .phase-status.json (seeded at _init, shared with
    // the plan-import join); a missing or malformed one falls back to the
    // snapshot's, then to a fresh mint persisted in the snapshot — the emitter
    // never writes the skill's own state file.
    const runId = UUID_RE.test(status.run_id)
      ? status.run_id
      : UUID_RE.test(snapshot?.runId)
        ? snapshot.runId
        : crypto.randomUUID();

    const ctx = {
      skill,
      runId,
      sessionId: UUID_RE.test(sessionId) ? sessionId : undefined,
      installId: await getInstallId(),
    };
    for (const event of events) {
      try {
        await post(endpoint, await buildRequest(event, ctx));
      } catch {
        // No retries by design: a retry queue is unbounded local state for
        // data that is loss-tolerant in aggregate. The snapshot still advances.
      }
    }

    // via/updatedAt are the hook-liveness tag: a future skill-invoked CLI step
    // reads them to skip its call when hooks are demonstrably doing the job,
    // and the idempotent diff makes the two paths safe even without the check.
    await fs.writeFile(
      snapshotFile,
      JSON.stringify(
        {
          runId,
          sessionId: ctx.sessionId ?? snapshot?.sessionId,
          phases: status.phases ?? {},
          completed: Boolean(snapshot?.completed) || status.current_phase === "complete",
          via: viaMode(),
          updatedAt: new Date().toISOString(),
        },
        null,
        2,
      ),
    );
  } finally {
    releaseLock(lock);
  }
}

// ---------------------------------------------------------------------- main

async function main() {
  const args = process.argv.slice(2);

  if (args[0] === "consent") {
    await runConsentCommand(args[1]);
    return;
  }

  if (process.env.DO_NOT_TRACK === "1") return;
  if (process.env.AWS_STARTUP_ADVISOR_TELEMETRY === "0") return;

  const endpoint = process.env.AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT;
  if (!endpoint) return; // nothing attempted, snapshots untouched — see header

  const sessionEndMode = args.includes("--session-end");
  const payload = await readStdin();
  const sessionId = payload?.session_id ?? payload?.conversation_id;

  // Post-write fast path: if the edited file is not under a .migration tree,
  // this invocation has no possible work.
  const editedPath = payload?.tool_input?.file_path ?? payload?.file_path;
  if (!sessionEndMode && !args.includes("--reconcile") && editedPath && !editedPath.includes(".migration")) {
    return;
  }

  const startDir =
    (editedPath ? path.dirname(editedPath) : undefined) ??
    payload?.cwd ??
    payload?.workspace_roots?.[0] ??
    process.cwd();

  for (const runDir of await findRunDirs(startDir)) {
    await processRun(runDir, { sessionId, sessionEndMode, endpoint });
  }
}

main()
  .catch(() => {})
  .finally(() => process.exit(0));
