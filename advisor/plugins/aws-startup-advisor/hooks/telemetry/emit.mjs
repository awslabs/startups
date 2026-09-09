#!/usr/bin/env node
// Migration telemetry emitter. Invoked by host hooks (Claude Code or Cursor),
// never by the agent, except for the consent subcommand and the CLI fallback:
//   node emit.mjs                    post-write: payload on stdin names the edited file
//   node emit.mjs --reconcile        end-of-turn: re-read state regardless of writer
//   node emit.mjs --session-end      teardown: final sweep for this session's runs
//   node emit.mjs consent <get|grant|revoke|status>
//
// Reads .migration/<id>/.phase-status.json, diffs it against the co-located
// .telemetry-snapshot.json, and POSTs one event per transition to the endpoint
// in AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT. Everything it needs is on disk:
// the run declares its owner via the owning_skill key in .phase-status.json,
// and a run with no declared owner emits nothing.
//
// Fail-open: every path exits 0 and surfaces nothing to the customer. The one
// deliberate exception to "the snapshot advances regardless" is a disabled
// endpoint (AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT set to empty): nothing was
// attempted, so the snapshot is left alone and the run is reported in full
// once sending is re-enabled.

import { promises as fs } from "node:fs";
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import os from "node:os";
import crypto from "node:crypto";
import { fileURLToPath } from "node:url";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MIGRATION_SKILLS = new Set(["GCP_TO_AWS", "HEROKU_TO_AWS", "LLM_TO_BEDROCK"]);
const LOCK_STALE_MS = 60_000;
const POST_TIMEOUT_MS = 3_000;

// Production endpoint, compiled in so a shipped plugin needs no user setup.
// AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT overrides it; setting the variable to
// an empty string disables sending entirely, and in that inert state snapshots
// are never advanced, so nothing is lost.
const DEFAULT_ENDPOINT =
  "https://us-east-1.prod.startup-advisor-extension.saws.activate.aws.dev/v1/plugin-telemetry-event";

function resolveEndpoint() {
  const env = process.env.AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT;
  if (env === undefined) return DEFAULT_ENDPOINT;
  return env === "" ? null : env;
}

// How this invocation was triggered: "hook" (default) or "cli" via --via cli,
// the flag the skill-driven fallback in INTERPRETER.md passes on hosts without hooks.
function viaMode() {
  const i = process.argv.indexOf("--via");
  return i !== -1 && process.argv[i + 1] === "cli" ? "cli" : "hook";
}

// ---------------------------------------------------------------- utilities

function readJson(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

// Absent and unreadable are different inputs: a missing snapshot means a new
// run, but a truncated one (a hook killed mid-write) must not, or the run is
// re-reported from RUN_STARTED.
const SNAPSHOT_UNREADABLE = Symbol("snapshot-unreadable");

function readSnapshot(file) {
  if (!existsSync(file)) return null;
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return SNAPSHOT_UNREADABLE;
  }
}

// Temp file plus rename, so a hook killed at the host's timeout cannot leave a
// half-written file where readSnapshot would find it.
function writeJson(file, value) {
  mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(value, null, 2));
  renameSync(tmp, file);
}

function pluginRoot() {
  // hooks/telemetry/emit.mjs → plugin root is two levels up.
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
}

function pluginVersion() {
  const manifest = readJson(path.join(pluginRoot(), ".claude-plugin", "plugin.json"));
  return typeof manifest?.version === "string" ? manifest.version : "0.0.0";
}

// Host detection. Cursor is checked first because it also exports Claude
// compatibility aliases (CLAUDE_PROJECT_DIR), so Claude Code markers are only
// trusted once Cursor is ruled out. Anything else reports OTHER rather than
// impersonating a known host: on hosts without hooks the emitter runs as a
// skill-invoked CLI, where a CLAUDE_CODE default would be wrong and undetectable.
function hostSource() {
  if (process.env.CURSOR_VERSION || process.env.CURSOR_PROJECT_DIR) return "CURSOR";
  if (process.env.CLAUDE_PLUGIN_ROOT || process.env.CLAUDECODE) return "CLAUDE_CODE";
  return "OTHER";
}

function stateDir() {
  return process.env.CLAUDE_PLUGIN_DATA || path.join(os.homedir(), ".aws-startups-plugins");
}

// installId is machine-level (one customer, many repos, one install), minted
// lazily on first use because there is no install-time hook to mint it at.
function getInstallId() {
  const file = path.join(stateDir(), "install.json");
  const existing = readJson(file);
  if (existing && UUID_RE.test(existing.installId)) return existing.installId;
  const installId = crypto.randomUUID();
  try {
    writeJson(file, { installId, createdAt: new Date().toISOString() });
  } catch {
    /* read-only state dir: still emit under the fresh id */
  }
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
// fallback: a decision can only be recorded where a migration tree exists, so
// consent never silently widens beyond the project the customer was asked about.
function consentFileFor(runDir) {
  return path.join(path.dirname(runDir), "telemetry.json");
}

function consentGrantedFor(runDir) {
  if (process.env.DO_NOT_TRACK === "1") return false;
  if (process.env.AWS_STARTUP_ADVISOR_TELEMETRY === "0") return false;
  return readJson(consentFileFor(runDir))?.consent === "granted";
}

// The skills routinely cd into .migration/<id>/ to work with relative paths, so
// the consent command must find the migration root from anywhere inside the
// project, not only from its root.
function findMigrationRoot(startDir) {
  let dir = path.resolve(startDir);
  for (let depth = 0; depth < 6; depth++) {
    if (path.basename(dir) === ".migration") return dir;
    const candidate = path.join(dir, ".migration");
    if (existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return path.resolve(".migration"); // nothing found: report against cwd
}

function runConsentCommand(action) {
  const migrationRoot = findMigrationRoot(process.cwd());
  const file = path.join(migrationRoot, "telemetry.json");
  const record = readJson(file);
  const write = (consent) => {
    if (!existsSync(migrationRoot)) {
      process.stdout.write("no .migration directory here; create the run first\n");
      return;
    }
    writeJson(file, {
      consent,
      installId: getInstallId(),
      consentedAt: new Date().toISOString(),
      version: 1,
    });
    process.stdout.write(`${consent}\n`);
  };
  switch (action) {
    case "get":
      process.stdout.write(`${record?.consent ?? "unset"}\n`);
      return;
    case "status": {
      const install = readJson(path.join(stateDir(), "install.json"));
      process.stdout.write(
        JSON.stringify(
          {
            consent: record?.consent ?? "unset",
            consentFile: file,
            stateDir: stateDir(),
            installId: install?.installId ?? "not yet minted",
            endpoint: resolveEndpoint() ?? "disabled",
          },
          null,
          2,
        ) + "\n",
      );
      return;
    }
    case "grant":
      write("granted");
      return;
    case "revoke":
      // A decline is a decision too: recorded locally so the customer is not
      // asked again. No event is sent for it.
      write("revoked");
      return;
    default:
      process.stdout.write("usage: emit.mjs consent <get|grant|revoke|status>\n");
  }
}

// ------------------------------------------------------------------- the lock

// Steps read-snapshot → POST → write-snapshot span network calls, and the
// post-write and reconcile triggers can overlap. An exclusive per-run lock
// (directory creation as atomic test-and-set) is the one duplication defence
// no downstream layer can substitute for: overlapping invocations would read
// the same "before" state and report the same transitions twice.
function acquireLock(runDir) {
  const lock = path.join(runDir, ".telemetry-lock");
  try {
    mkdirSync(lock);
    return lock;
  } catch (err) {
    if (err?.code !== "EEXIST") return null; // unwritable dir: emit nothing
    try {
      if (Date.now() - statSync(lock).mtimeMs > LOCK_STALE_MS) {
        rmSync(lock, { recursive: true, force: true });
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
    rmSync(lock, { recursive: true, force: true });
  } catch {
    /* already gone */
  }
}

// ------------------------------------------------------ model vocabularies

// Every value sent is checked against the model's enums before it leaves: the
// service rejects a whole request on one unknown member, so an unmapped value
// is omitted (or, for a phase name, the event is skipped) rather than sent.
const PHASES = new Set(["DISCOVER", "CLARIFY", "DESIGN", "ESTIMATE", "WORKSHOP", "GENERATE", "FEEDBACK"]);

// Statuses that resolve a phase. The DSL lets a skill resolve a phase without
// running it (skipped, not_applicable); those are transitions to report too.
const RESOLVED_STATUS = {
  completed: "SUCCESS",
  skipped: "SKIPPED",
  not_applicable: "NOT_APPLICABLE",
  failed: "FAILED",
};

const RUN_MODE = { decide: "DECIDE", decide_and_execute: "DECIDE_AND_EXECUTE" };

const mapEnum = (table, value) => (value == null ? undefined : table[String(value).toLowerCase()]);

const PRICING_SOURCE = {
  live: "LIVE",
  cached: "CACHED",
  cached_fallback: "CACHED_FALLBACK",
  cached_stale: "CACHED_STALE",
  unavailable: "UNAVAILABLE",
};

const RECOMMENDATION_OUTCOME = { go: "GO", conditional_go: "CONDITIONAL_GO", defer: "DEFER", stay: "STAY" };

const CLARIFY_MODE = { fast: "FAST", wizard: "WIZARD", full: "FULL", ai_only: "AI_ONLY" };

// Mirrors the `current_costs.source` vocabulary the skills write.
// estimated_from_token_volume is the AI route (it prices tokens, not
// infrastructure); preferences is a defaulted placeholder, kept apart from
// USER_PROVIDED so a default is never read as the customer's own figure.
const SPEND_BASIS = {
  billing_data: "BILLING_DATA",
  inventory_estimate: "INVENTORY_ESTIMATE",
  live_prices_plus_cache: "LIVE_PRICES_PLUS_CACHE",
  pricing_cache: "PRICING_CACHE",
  user_provided: "USER_PROVIDED",
  unavailable: "UNAVAILABLE",
  estimated_from_token_volume: "TOKEN_VOLUME_ESTIMATE",
  preferences: "DEFAULTED",
};

// ------------------------------------------------------ attribute derivation

// Pricing provenance is written either as a bare string or as an object
// { status, fallback_staleness: { is_stale } }; CACHED_STALE is composed from
// the object form.
function toPricingSource(raw) {
  if (raw == null) return undefined;
  const isObject = typeof raw === "object";
  const mapped = mapEnum(PRICING_SOURCE, isObject ? raw.status : raw);
  if (!mapped) return undefined;
  const stale = isObject && raw.fallback_staleness?.is_stale === true;
  return mapped === "CACHED" && stale ? "CACHED_STALE" : mapped;
}

// Matched against resource TYPES only, never the serialised inventory: the
// inventory carries discovery metadata such as classification_source:
// "llm_inference", which would read as "the customer runs AI".
const AI_TYPE =
  /vertex|aiplatform|notebooks|discovery_engine|automl|ml_engine|dialogflow|document_ai|bedrock|sagemaker|comprehend/;
const DB_TYPE =
  /sql|postgres|mysql|mongo|redis|firestore|spanner|bigtable|datastore|memorystore|alloydb|rds|aurora|dynamo|elasticache|documentdb/;

const resourceTypes = (resources) =>
  resources
    .map((r) => String(r?.type ?? r?.resource_type ?? ""))
    .join(" ")
    .toLowerCase();

// Monthly spend on the SOURCE platform. The key name varies by skill, phase and
// route; total_monthly_spend is the billing-only route's MEASURED figure.
const SOURCE_SPEND_KEYS = [
  "gcp_monthly_spend",
  "gcp_monthly",
  "gcp_monthly_usd",
  "total_monthly_spend",
  "gcp_total_monthly",
  "total_monthly",
  "gcp_monthly_ai_spend",
  "total_current_ai_monthly",
  "heroku_monthly",
  "heroku_monthly_estimated",
];

function toSpendBand(amount) {
  if (typeof amount !== "number" || !Number.isFinite(amount) || amount < 0) return undefined;
  if (amount < 100) return "UNDER_100";
  if (amount < 1000) return "FROM_100_TO_1K";
  if (amount < 10000) return "FROM_1K_TO_10K";
  return "OVER_10K";
}

const SKILL_INVENTORY = {
  GCP_TO_AWS: { inventory: "gcp-resource-inventory.json", provider: "GCP" },
  HEROKU_TO_AWS: { inventory: "heroku-resource-inventory.json", provider: "HEROKU" },
};

// Every estimation artifact present, in preference order: an AI-primary run
// writes both infra and AI files, and each attribute is taken from the first
// artifact that actually supplies it.
const readEstimates = (dir) =>
  ["estimation-infra.json", "estimation-ai.json", "estimation-billing.json"]
    .map((name) => readJson(path.join(dir, name)))
    .filter(Boolean);

// The infra and AI routes record source cost under current_costs; the
// billing-only route under gcp_baseline.
const costContainer = (estimate) => estimate.current_costs ?? estimate.gcp_baseline ?? {};

// Attributes are lookups over the run's own artifacts, no inference. Phase
// facts attach only to the PHASE_COMPLETED event of the phase that produced
// them, so a terminal event never restates them and no aggregation double
// counts.
function deriveAttributes(runDir, skill, event) {
  const attributes = {};
  const spec = SKILL_INVENTORY[skill];
  if (spec) attributes.sourceProvider = spec.provider;

  const phaseEvent = event.eventName === "PHASE_COMPLETED";

  if (phaseEvent && event.phase === "DISCOVER") {
    const inventory = spec ? readJson(path.join(runDir, spec.inventory)) : null;
    const resources = Array.isArray(inventory) ? inventory : inventory?.resources;
    // App-code AI detection lives only here; it is what lets an AI workload
    // with no AI resource (an SDK called from application code) report hasAi.
    const aiProfile = readJson(path.join(runDir, "ai-workload-profile.json"));
    const aiFromProfile = Array.isArray(aiProfile?.models)
      ? aiProfile.models.length > 0
      : (aiProfile?.summary?.total_models_detected ?? 0) > 0;

    if (Array.isArray(resources)) {
      attributes.resourceCount = Math.min(resources.length, 10000); // model @range
      const types = resourceTypes(resources);
      attributes.hasDatabase = DB_TYPE.test(types);
      attributes.hasAi = AI_TYPE.test(types) || aiFromProfile;
    } else if (aiProfile) {
      attributes.hasAi = aiFromProfile;
    }
  }

  if (phaseEvent && event.phase === "CLARIFY") {
    const preferences = readJson(path.join(runDir, "preferences.json"));
    const clarifyMode = mapEnum(CLARIFY_MODE, preferences?.metadata?.migration_type);
    if (clarifyMode) attributes.clarifyMode = clarifyMode;
  }

  if (phaseEvent && event.phase === "ESTIMATE") {
    const estimates = readEstimates(runDir);
    for (const estimate of estimates) {
      if (!attributes.recommendationOutcome) {
        const outcome = mapEnum(RECOMMENDATION_OUTCOME, estimate.recommendation?.outcome);
        if (outcome) attributes.recommendationOutcome = outcome;
      }
      if (!attributes.pricingSource) {
        const pricing = toPricingSource(estimate.pricing_source ?? estimate.projected_costs?.pricing_source);
        if (pricing) attributes.pricingSource = pricing;
      }
    }
    // spendBand and spendBasis travel as a pair from the same container: a
    // band without its basis is indistinguishable from a measured figure. A
    // basis alone is harmless and is still reported.
    for (const estimate of estimates) {
      const container = costContainer(estimate);
      const basis = mapEnum(SPEND_BASIS, container.source);
      let band;
      for (const key of SOURCE_SPEND_KEYS) {
        band = toSpendBand(container[key]);
        if (band) break;
      }
      if (basis && band) {
        attributes.spendBand = band;
        attributes.spendBasis = basis;
        break;
      }
      if (basis && !attributes.spendBasis) attributes.spendBasis = basis;
    }
  }

  if (event.runMode) attributes.runMode = event.runMode;

  return Object.keys(attributes).length ? attributes : undefined;
}

// ------------------------------------------------------------------- the diff

// One event per transition between the snapshot and .phase-status.json.
// Pending/in_progress churn emits nothing; a phase name outside the model's
// enum emits nothing for that phase. RUN_COMPLETED is gated on the snapshot's
// completed flag, not the transition, so a current_phase that leaves
// "complete" and returns cannot mint a second terminal event.
function diffEvents(status, snapshot) {
  const events = [];
  if (!snapshot) events.push({ eventName: "RUN_STARTED" });
  const before = snapshot?.phases ?? {};
  for (const [name, state] of Object.entries(status.phases ?? {})) {
    if (before[name] === state) continue;
    const mapped = RESOLVED_STATUS[String(state).toLowerCase()];
    const phase = String(name).toUpperCase();
    if (!mapped || !PHASES.has(phase)) continue;
    events.push({ eventName: "PHASE_COMPLETED", phase, status: mapped });
  }
  if (status.current_phase === "complete" && !snapshot?.completed) {
    const runMode = mapEnum(RUN_MODE, status.run_mode);
    events.push({ eventName: "RUN_COMPLETED", status: "SUCCESS", ...(runMode ? { runMode } : {}) });
  }
  return events;
}

// ----------------------------------------------------------------- the envelope

// eventId is not sent: the service mints one per received request for
// SQS-redelivery dedup, and one POST per event with no retries makes that
// equivalent to minting it here.
function buildRequest(event, ctx) {
  const attributes = deriveAttributes(ctx.runDir, ctx.skill, event);
  const migrationActivity = {
    eventName: event.eventName,
    skill: ctx.skill,
    ...(ctx.initiatingSkill ? { initiatingSkill: ctx.initiatingSkill } : {}),
    runId: ctx.runId,
    ...(ctx.sessionId ? { sessionId: ctx.sessionId } : {}),
    ...(event.phase ? { phase: event.phase } : {}),
    ...(event.status ? { status: event.status } : {}),
    ...(attributes ? { attributes } : {}),
  };
  return {
    installId: ctx.installId,
    source: hostSource(),
    pluginVersion: ctx.pluginVersion,
    occurredAt: Date.now(),
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
  const status = readJson(path.join(runDir, ".phase-status.json"));
  if (!status?.migration_id) return;

  // Attribution is read from disk, never from an argument: a run that declares
  // no owner, or an owner outside the migration set, emits nothing (fail closed)
  // rather than emitting under the wrong skill.
  const skill = status.owning_skill;
  if (!MIGRATION_SKILLS.has(skill)) return;

  if (!consentGrantedFor(runDir)) return;

  const snapshotFile = path.join(runDir, ".telemetry-snapshot.json");
  const lock = acquireLock(runDir);
  if (!lock) return;
  try {
    const snapshot = readSnapshot(snapshotFile);
    if (snapshot === SNAPSHOT_UNREADABLE) return; // try again on the next trigger

    // Teardown sweeps only the session that wrote the snapshot; a run last
    // touched by another session is that session's to report.
    if (sessionEndMode && snapshot && sessionId && snapshot.sessionId !== sessionId) return;

    const events = diffEvents(status, snapshot);
    if (events.length === 0) return;

    // Identifiers read back from customer-editable files are validated, not
    // trusted: the service rejects the whole event on one malformed UUID.
    // run_id comes from .phase-status.json (seeded at _init); a missing or
    // malformed one falls back to the snapshot's, then to a fresh mint persisted
    // in the snapshot. The emitter never writes the skill's own state file.
    const runId = UUID_RE.test(status.run_id)
      ? status.run_id
      : UUID_RE.test(snapshot?.runId)
        ? snapshot.runId
        : crypto.randomUUID();

    const ctx = {
      runDir,
      skill,
      // Only a known migration skill may be named as the invoker; anything else
      // is dropped rather than risk rejecting the whole event.
      initiatingSkill: MIGRATION_SKILLS.has(status.initiated_by) ? status.initiated_by : undefined,
      runId,
      sessionId: UUID_RE.test(sessionId) ? sessionId : undefined,
      installId: getInstallId(),
      pluginVersion: pluginVersion(),
    };

    // Concurrently, under one budget: sent serially, a reconcile catching a
    // whole run could outlive the host's hook timeout and never reach the
    // snapshot write, so the next trigger would repeat the batch. No retries by
    // design: a retry queue is unbounded local state for data that is
    // loss-tolerant in aggregate.
    await Promise.allSettled(events.map((event) => post(endpoint, buildRequest(event, ctx))));

    // via/updatedAt are the hook-liveness tag: the skill-driven CLI fallback
    // reads them to skip its call when a hook reported recently, and the
    // idempotent diff keeps the two paths safe even without that check.
    writeJson(snapshotFile, {
      runId,
      sessionId: ctx.sessionId ?? snapshot?.sessionId,
      phases: status.phases ?? {},
      completed: Boolean(snapshot?.completed) || status.current_phase === "complete",
      via: viaMode(),
      updatedAt: new Date().toISOString(),
    });
  } finally {
    releaseLock(lock);
  }
}

// ---------------------------------------------------------------------- main

async function main() {
  const args = process.argv.slice(2);

  if (args[0] === "consent") {
    runConsentCommand(args[1]);
    return;
  }

  if (process.env.DO_NOT_TRACK === "1") return;
  if (process.env.AWS_STARTUP_ADVISOR_TELEMETRY === "0") return;

  const endpoint = resolveEndpoint();
  if (!endpoint) return; // explicitly disabled: nothing attempted, snapshots untouched

  const sessionEndMode = args.includes("--session-end");
  const payload = await readStdin();
  // Claude Code sends session_id on every hook; Cursor sends conversation_id
  // on tool, file and stop hooks.
  const sessionId = payload?.session_id ?? payload?.conversation_id;

  // Post-write fast path: if the edited file is not under a .migration tree,
  // this invocation has no possible work.
  const editedPath = payload?.tool_input?.file_path ?? payload?.file_path;
  if (!sessionEndMode && !args.includes("--reconcile") && editedPath && !editedPath.includes(".migration")) {
    return;
  }

  // Start discovery at the directory that owns the .migration tree, so an
  // edit deep inside a run's artifacts still resolves to its run.
  const marker = editedPath ? editedPath.indexOf(`${path.sep}.migration${path.sep}`) : -1;
  const startDir =
    (marker !== -1 ? editedPath.slice(0, marker) : undefined) ??
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
