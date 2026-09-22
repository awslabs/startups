// Executing-path tests for the telemetry emitter (hooks/telemetry/emit.mjs).
//
// Each test builds an ephemeral project with a .migration/ run and a consent
// record, points the emitter at a local HTTP stub, runs it exactly as a hook
// would (node emit.mjs --reconcile, hook payload on stdin) and asserts on the
// requests the stub received and the snapshot left on disk. Nothing inside the
// emitter is mocked.
//
// Run: node --test tests/hooks/telemetry-emitter.test.ts

import { after, before, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer, type Server } from 'node:http';
import type { AddressInfo } from 'node:net';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, utimesSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { readFileSync as readText } from 'node:fs';
import { tmpdir } from 'node:os';

const EMIT = join(import.meta.dirname, '../../hooks/telemetry/emit.mjs');
const RUN_ID = '3f9c2a7e-5b1d-4e8a-9c6f-2d7b8e1a4c53';
const SESSION_ID = '9b2c4d6e-8f10-4a12-b345-6789abcdef01';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Received = { body: any };

let server: Server;
let endpoint: string;
const received: Received[] = [];
// What the stub answers; a test flips it to 403 or 429 to stand in for the
// service's closed launch gate or a throttle, or decides per request body.
let respondWith = 200;
let respondFor: (body: any) => number = () => respondWith;

before(async () => {
  server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      received.push({ body });
      res.writeHead(respondFor(body)).end();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  endpoint = `http://127.0.0.1:${(server.address() as AddressInfo).port}/v1/plugin-telemetry-event`;
});

after(() => server.close());

interface Project {
  root: string;
  runDir: string;
  stateDir: string;
  statusFile: string;
  consentFile: string;
}

function phaseStatus(overrides: Record<string, unknown> = {}) {
  return {
    migration_id: '0226-1430',
    run_id: RUN_ID,
    owning_skill: 'GCP_TO_AWS',
    last_updated: '2026-02-26T15:35:22Z',
    current_phase: 'clarify',
    phases: {
      discover: 'completed',
      clarify: 'in_progress',
      design: 'pending',
      estimate: 'pending',
      workshop: 'pending',
      generate: 'pending',
      feedback: 'pending',
    },
    ...overrides,
  };
}

// Consent is written before the state file, the order `_init` uses (run
// directory, consent, then phase status), so the run reads as live rather than
// as pre-consent history.
function makeProject(status: Record<string, unknown>, consent: 'granted' | 'revoked' | null = 'granted'): Project {
  const root = mkdtempSync(join(tmpdir(), 'emit-project-'));
  const runDir = join(root, '.migration', '0226-1430');
  mkdirSync(runDir, { recursive: true });
  const consentFile = join(root, '.migration', 'telemetry.json');
  if (consent) {
    writeFileSync(
      consentFile,
      JSON.stringify({ consent, installId: RUN_ID, consentedAt: new Date().toISOString(), version: 1 }),
    );
  }
  const statusFile = join(runDir, '.phase-status.json');
  writeFileSync(statusFile, JSON.stringify(status, null, 2));
  return { root, runDir, stateDir: mkdtempSync(join(tmpdir(), 'emit-state-')), statusFile, consentFile };
}

function cleanup(p: Project) {
  rmSync(p.root, { recursive: true, force: true });
  rmSync(p.stateDir, { recursive: true, force: true });
}

// Run the emitter the way the Stop hook does and return only the requests this
// invocation produced.
async function reconcile(p: Project): Promise<any[]> {
  const before = received.length;
  const env = { ...process.env };
  delete env.DO_NOT_TRACK;
  delete env.AWS_STARTUP_ADVISOR_TELEMETRY;
  delete env.CURSOR_VERSION;
  delete env.CURSOR_PROJECT_DIR;
  Object.assign(env, {
    AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT: endpoint,
    CLAUDE_PLUGIN_DATA: p.stateDir,
    CLAUDECODE: '1',
  });
  const child = spawn(process.execPath, [EMIT, '--reconcile'], { cwd: p.root, env, stdio: ['pipe', 'ignore', 'inherit'] });
  child.stdin.end(JSON.stringify({ session_id: SESSION_ID, cwd: p.root }));
  const code = await new Promise<number | null>((resolve) => child.on('close', resolve));
  assert.equal(code, 0, 'the emitter is fail-open and always exits 0');
  return received.slice(before).map((r) => r.body);
}

const activity = (body: any) => body.pluginTelemetryEvent.migrationActivity;
const snapshotOf = (p: Project) => JSON.parse(readFileSync(join(p.runDir, '.telemetry-snapshot.json'), 'utf8'));

describe('telemetry emitter', () => {
  it('reports a new run once: RUN_STARTED plus the phases already resolved, under the state file run_id', async () => {
    // Arrange
    const p = makeProject(phaseStatus());
    try {
      // Act
      const first = await reconcile(p);
      const second = await reconcile(p);

      // Assert
      assert.deepEqual(
        first.map((b) => [activity(b).eventName, activity(b).phase, activity(b).status]).sort(),
        [
          ['PHASE_COMPLETED', 'DISCOVER', 'SUCCESS'],
          ['RUN_STARTED', undefined, undefined],
        ],
      );
      for (const body of first) {
        assert.equal(activity(body).runId, RUN_ID);
        assert.equal(activity(body).skill, 'GCP_TO_AWS');
        assert.equal(activity(body).sessionId, SESSION_ID);
        assert.equal(body.source, 'CLAUDE_CODE');
        assert.match(body.installId, UUID);
        assert.equal(typeof body.occurredAt, 'number');
        assert.equal(activity(body).attributes?.sourceProvider, 'GCP');
      }
      assert.deepEqual(second, [], 'an unchanged run is not re-reported');
      assert.equal(snapshotOf(p).runId, RUN_ID);
    } finally {
      cleanup(p);
    }
  });

  it('sends a run_id that macOS uuidgen minted in upper case in lower case, the only form the data lake accepts', async () => {
    // Arrange
    const p = makeProject(phaseStatus({ run_id: RUN_ID.toUpperCase() }));
    try {
      // Act
      const bodies = await reconcile(p);

      // Assert
      assert.equal(bodies.length, 2);
      for (const body of bodies) assert.equal(activity(body).runId, RUN_ID);
      assert.equal(snapshotOf(p).runId, RUN_ID);
    } finally {
      cleanup(p);
    }
  });

  it('reports each later transition exactly once and the terminal event with its run mode', async () => {
    // Arrange
    const p = makeProject(phaseStatus());
    try {
      await reconcile(p);
      const status = phaseStatus({
        current_phase: 'complete',
        run_mode: 'decide',
        phases: { ...phaseStatus().phases, clarify: 'completed', design: 'completed', estimate: 'completed' },
      });
      writeFileSync(p.statusFile, JSON.stringify(status, null, 2));

      // Act
      const events = await reconcile(p);
      const again = await reconcile(p);

      // Assert
      assert.deepEqual(
        events.map((b) => [activity(b).eventName, activity(b).phase ?? activity(b).attributes?.runMode]).sort(),
        [
          ['PHASE_COMPLETED', 'CLARIFY'],
          ['PHASE_COMPLETED', 'DESIGN'],
          ['PHASE_COMPLETED', 'ESTIMATE'],
          ['RUN_COMPLETED', 'DECIDE'],
        ],
      );
      assert.deepEqual(again, []);
      assert.equal(snapshotOf(p).completed, true);
    } finally {
      cleanup(p);
    }
  });

  it('sends nothing and leaves no trace without granted consent', async () => {
    // Arrange
    const revoked = makeProject(phaseStatus(), 'revoked');
    const unset = makeProject(phaseStatus(), null);
    try {
      // Act + Assert
      assert.deepEqual(await reconcile(revoked), []);
      assert.deepEqual(await reconcile(unset), []);
      assert.equal(existsSync(join(revoked.runDir, '.telemetry-snapshot.json')), false);
      assert.equal(existsSync(join(unset.runDir, '.telemetry-snapshot.json')), false);
    } finally {
      cleanup(revoked);
      cleanup(unset);
    }
  });

  it('sends nothing for a run that names no owning skill', async () => {
    // Arrange
    const status = phaseStatus();
    delete (status as Record<string, unknown>).owning_skill;
    const p = makeProject(status);
    try {
      // Act + Assert
      assert.deepEqual(await reconcile(p), []);
    } finally {
      cleanup(p);
    }
  });

  it('reports a run whose state was written moments before consent: a near tie is live, not history', async () => {
    // Arrange: state first, consent 50 ms later, as a slow host or coarse
    // filesystem timestamp would order them
    const p = makeProject(phaseStatus(), null);
    try {
      await new Promise((r) => setTimeout(r, 50));
      writeFileSync(
        p.consentFile,
        JSON.stringify({ consent: 'granted', installId: RUN_ID, consentedAt: new Date().toISOString(), version: 1 }),
      );

      // Act
      const events = await reconcile(p);

      // Assert
      assert.equal(events.length, 2, 'RUN_STARTED and DISCOVER are reported');
    } finally {
      cleanup(p);
    }
  });

  it('holds the snapshot while the service refuses with 403, then reports the run in full once it accepts', async () => {
    // Arrange
    const p = makeProject(phaseStatus());
    try {
      // Act: the gate is closed for the first reconcile and open for the second
      respondWith = 403;
      const refused = await reconcile(p);
      const snapshotWhileRefused = existsSync(join(p.runDir, '.telemetry-snapshot.json'));
      respondWith = 200;
      const accepted = await reconcile(p);
      const again = await reconcile(p);

      // Assert
      assert.equal(refused.length, 2, 'the events were attempted');
      assert.equal(snapshotWhileRefused, false, 'but nothing was recorded as reported');
      assert.deepEqual(
        accepted.map((b) => [activity(b).eventName, activity(b).phase]).sort(),
        [['PHASE_COMPLETED', 'DISCOVER'], ['RUN_STARTED', undefined]],
        'the same events are sent again once accepted',
      );
      assert.deepEqual(again, []);
      assert.equal(snapshotOf(p).runId, RUN_ID);
    } finally {
      respondWith = 200;
      cleanup(p);
    }
  });

  it('re-sends only the throttled events of a batch, never the accepted ones', async () => {
    // Arrange: RUN_STARTED is accepted, the phase event in the same batch gets a 429
    const p = makeProject(phaseStatus());
    try {
      respondFor = (body) => (activity(body).eventName === 'PHASE_COMPLETED' ? 429 : 200);
      const first = await reconcile(p);
      respondFor = () => 200;

      // Act
      const replay = await reconcile(p);
      const again = await reconcile(p);

      // Assert
      assert.equal(first.length, 2, 'both were attempted');
      assert.deepEqual(
        replay.map((b) => [activity(b).eventName, activity(b).phase]),
        [['PHASE_COMPLETED', 'DISCOVER']],
        'only the throttled event is sent again',
      );
      assert.deepEqual(again, []);
      assert.equal(snapshotOf(p).phases.discover, 'completed');
    } finally {
      respondFor = () => respondWith;
      cleanup(p);
    }
  });

  it('re-sends RUN_STARTED alone when it was the one refused', async () => {
    // Arrange: the phase event is accepted, RUN_STARTED gets a 503
    const p = makeProject(phaseStatus());
    try {
      respondFor = (body) => (activity(body).eventName === 'RUN_STARTED' ? 503 : 200);
      await reconcile(p);
      respondFor = () => 200;

      // Act
      const replay = await reconcile(p);

      // Assert
      assert.deepEqual(replay.map((b) => activity(b).eventName), ['RUN_STARTED']);
      assert.equal(snapshotOf(p).started, true);
    } finally {
      respondFor = () => respondWith;
      cleanup(p);
    }
  });

  it('honours a plugin-wide consent record before the project one, either way', async () => {
    // Arrange: no project consent, but the plugin-wide record (in the plugin data dir) says granted
    const granted = makeProject(phaseStatus(), null);
    writeFileSync(
      join(granted.stateDir, 'telemetry.json'),
      JSON.stringify({ consent: 'granted', installId: RUN_ID, consentedAt: new Date(Date.now() - 60_000).toISOString(), version: 1 }),
    );
    // and a project that said yes while the plugin-wide record says no
    const overruled = makeProject(phaseStatus(), 'granted');
    writeFileSync(
      join(overruled.stateDir, 'telemetry.json'),
      JSON.stringify({ consent: 'revoked', installId: RUN_ID, consentedAt: new Date().toISOString(), version: 1 }),
    );
    try {
      // Act + Assert
      assert.equal((await reconcile(granted)).length, 2, 'plugin-wide yes is enough');
      assert.deepEqual(await reconcile(overruled), [], 'plugin-wide no wins over a project yes');
    } finally {
      cleanup(granted);
      cleanup(overruled);
    }
  });

  it('treats a run last written before consent as history: baselines it silently, then reports only new transitions', async () => {
    // Arrange: the state file predates the consent record by a day
    const p = makeProject(phaseStatus());
    const dayAgo = new Date(Date.now() - 24 * 3600 * 1000);
    utimesSync(p.statusFile, dayAgo, dayAgo);
    try {
      // Act
      const first = await reconcile(p);
      writeFileSync(
        p.statusFile,
        JSON.stringify(phaseStatus({ current_phase: 'design', phases: { ...phaseStatus().phases, clarify: 'completed' } }), null, 2),
      );
      const later = await reconcile(p);

      // Assert
      assert.deepEqual(first, [], 'pre-consent history is not reported');
      assert.deepEqual(snapshotOf(p).phases.discover, 'completed', 'but it is recorded as already known');
      assert.deepEqual(
        later.map((b) => [activity(b).eventName, activity(b).phase]),
        [['PHASE_COMPLETED', 'CLARIFY']],
        'no RUN_STARTED is invented for a run that started before consent',
      );
    } finally {
      cleanup(p);
    }
  });
});

// The consent step is written out in two places: the shared interpreter's _init,
// which the DSL-governed skills run, and gcp-to-aws's own discover.md, which does
// its run setup without the interpreter. Customers must see one wording wherever
// the step appears, so the two must not drift. Compared from "Locate the emitter"
// to the ordering sentence,
// with indentation removed, since the two files nest the step differently.
describe('consent step wording', () => {
  const SKILLS = join(import.meta.dirname, '../../skills');
  const consentStep = (file: string) => {
    const text = readText(file, 'utf8');
    const start = text.indexOf('Locate the emitter.');
    const end = text.indexOf('This ordering (run directory first', start);
    assert.ok(start !== -1 && end !== -1, `consent step not found in ${file}`);
    return text
      .slice(start, end)
      .split('\n')
      .map((line) => line.replace(/^\s+/, ''))
      .join('\n');
  };

  it('is identical in the shared interpreter and in gcp-to-aws discover.md', () => {
    // Act + Assert
    assert.equal(
      consentStep(join(SKILLS, 'gcp-to-aws/references/phases/discover/discover.md')),
      consentStep(join(SKILLS, 'shared/dsl/INTERPRETER.md')),
    );
  });
});

// Cursor registration: the manifest must point at the Cursor hooks file, and every
// command must reach the emitter through ${CURSOR_PLUGIN_ROOT}, the form Cursor's own
// plugins use; a plugin-root-relative path is not documented to resolve.
describe('cursor registration', () => {
  const PLUGIN = join(import.meta.dirname, '../..');
  const manifest = JSON.parse(readText(join(PLUGIN, '.cursor-plugin/plugin.json'), 'utf8'));
  const hooks = JSON.parse(readText(join(PLUGIN, 'hooks/telemetry/cursor/hooks.json'), 'utf8'));

  it('wires the manifest to the Cursor hooks file and the marketplace to the plugin', () => {
    // Act + Assert
    assert.equal(manifest.hooks, 'hooks/telemetry/cursor/hooks.json');
    assert.ok(existsSync(join(PLUGIN, manifest.hooks)));
    const marketplace = JSON.parse(readText(join(PLUGIN, '../../../.cursor-plugin/marketplace.json'), 'utf8'));
    const entry = marketplace.plugins.find((p: { name: string }) => p.name === manifest.name);
    assert.ok(entry, 'the root marketplace lists this plugin');
    assert.ok(existsSync(join(PLUGIN, '../../..', entry.source, '.cursor-plugin/plugin.json')));
  });

  it('reaches the emitter through CURSOR_PLUGIN_ROOT in every hook command', () => {
    // Act + Assert
    assert.equal(hooks.version, 1);
    const modes: Record<string, string> = { afterFileEdit: '--reconcile', stop: '--reconcile', sessionEnd: '--session-end' };
    assert.deepEqual(Object.keys(hooks.hooks).sort(), Object.keys(modes).sort());
    for (const [event, flag] of Object.entries(modes)) {
      for (const hook of hooks.hooks[event]) {
        assert.equal(hook.command, `node "\${CURSOR_PLUGIN_ROOT}/hooks/telemetry/emit.mjs" ${flag}`);
      }
    }
  });
});
