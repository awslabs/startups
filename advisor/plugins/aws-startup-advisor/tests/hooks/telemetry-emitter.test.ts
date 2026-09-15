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
import { tmpdir } from 'node:os';

const EMIT = join(import.meta.dirname, '../../hooks/telemetry/emit.mjs');
const RUN_ID = '3f9c2a7e-5b1d-4e8a-9c6f-2d7b8e1a4c53';
const SESSION_ID = '9b2c4d6e-8f10-4a12-b345-6789abcdef01';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Received = { body: any };

let server: Server;
let endpoint: string;
const received: Received[] = [];

before(async () => {
  server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      received.push({ body: JSON.parse(Buffer.concat(chunks).toString('utf8')) });
      res.writeHead(200).end();
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

function makeProject(status: Record<string, unknown>, consent: 'granted' | 'revoked' | null = 'granted'): Project {
  const root = mkdtempSync(join(tmpdir(), 'emit-project-'));
  const runDir = join(root, '.migration', '0226-1430');
  mkdirSync(runDir, { recursive: true });
  const statusFile = join(runDir, '.phase-status.json');
  writeFileSync(statusFile, JSON.stringify(status, null, 2));
  const consentFile = join(root, '.migration', 'telemetry.json');
  if (consent) {
    // Dated a minute before the state file: the emitter treats state last written
    // before consent as history, and the two writes above can straddle a
    // millisecond under load.
    const consentedAt = new Date(Date.now() - 60_000).toISOString();
    writeFileSync(consentFile, JSON.stringify({ consent, installId: RUN_ID, consentedAt, version: 1 }));
  }
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
