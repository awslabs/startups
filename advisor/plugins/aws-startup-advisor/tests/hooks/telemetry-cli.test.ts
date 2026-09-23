// Exercise the installed CLI entry points against a local HTTP receiver.
import { after, before, describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';

const REPO = resolve(import.meta.dirname, '../../../../..');
const PLUGINS = ['advisor/plugins/aws-startup-advisor', 'migrate/plugins/migration-to-aws'];
const RUN_ID = '3f9c2a7e-5b1d-4e8a-9c6f-2d7b8e1a4c53';
const HOOK = join(REPO, PLUGINS[0], 'hooks/telemetry/emit.mjs');
const CLI = join(REPO, PLUGINS[0], 'skills/gcp-to-aws/references/vendored/telemetry/emit.mjs');
const received: any[] = [];
let endpoint: string;
let respondFor = (_body: any) => 200;
const server = createServer((req, res) => {
  const chunks: Buffer[] = [];
  req.on('data', (chunk) => chunks.push(chunk));
  req.on('end', () => {
    const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    received.push(body);
    res.writeHead(respondFor(body)).end();
  });
});

before(async () => {
  await new Promise<void>((done) => server.listen(0, '127.0.0.1', done));
  const address = server.address();
  assert.ok(address && typeof address !== 'string');
  endpoint = `http://127.0.0.1:${address.port}/telemetry`;
});
after(() => server.close());

function project(skill = 'GCP_TO_AWS', consent: string | null = 'granted') {
  const root = mkdtempSync(join(tmpdir(), 'telemetry-cli-'));
  const run = join(root, '.migration', 'test-run');
  mkdirSync(run, { recursive: true });
  const consentFile = join(root, '.migration', 'telemetry.json');
  if (consent) writeFileSync(consentFile, JSON.stringify({
    consent, consentedAt: new Date(Date.now() - 60_000).toISOString(),
  }));
  const state = {
    migration_id: 'test-run', run_id: RUN_ID, owning_skill: skill,
    current_phase: 'discover', phases: { discover: 'in_progress', clarify: 'pending' },
  };
  const status = join(run, '.phase-status.json');
  writeFileSync(status, JSON.stringify(state));
  return { root, run, status, state, consentFile, snapshot: join(run, '.telemetry-snapshot.json') };
}
type Project = ReturnType<typeof project>;
const cleanup = (p: Project) => rmSync(p.root, { recursive: true, force: true });
const readSnapshot = (p: Project) => JSON.parse(readFileSync(p.snapshot, 'utf8'));
const activity = (body: any) => body.pluginTelemetryEvent.migrationActivity;
const save = (p: Project) => writeFileSync(p.status, JSON.stringify(p.state));

async function invoke(p: Project, options: {
  emitter?: string; args?: string[]; markers?: Record<string, string>;
  keepStdinOpen?: boolean; cwd?: string;
} = {}) {
  const env = { ...process.env };
  for (const key of Object.keys(env)) {
    if (/^(CLAUDE|CURSOR|AWS_STARTUP_ADVISOR_TELEMETRY)/.test(key) || key === 'DO_NOT_TRACK') delete env[key];
  }
  Object.assign(env, {
    // Isolate child-process home lookups from real plugin-wide consent and install identity.
    HOME: p.root,
    CLAUDE_PLUGIN_DATA: join(p.root, 'plugin-data'),
    AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT: endpoint,
  }, options.markers);
  const start = received.length;
  const child = spawn(process.execPath, [
    options.emitter ?? CLI, ...(options.args ?? ['--reconcile', '--via', 'cli']),
  ], { cwd: options.cwd ?? p.root, env, stdio: ['pipe', 'pipe', 'pipe'], timeout: 5000 });
  let stdout = '';
  let stderr = '';
  child.stdout.on('data', (chunk) => stdout += chunk);
  child.stderr.on('data', (chunk) => stderr += chunk);
  if (!options.keepStdinOpen) child.stdin.end();
  const code = await new Promise<number | null>((done, reject) => {
    child.once('error', reject);
    child.once('close', done);
  });
  assert.equal(code, 0, stderr);
  return { bodies: received.slice(start), stdout };
}

describe('telemetry CLI host routing', () => {
  for (const markers of [
    { CLAUDECODE: '1' },
    { CLAUDE_PLUGIN_ROOT: '/fixture/plugin' },
    { CURSOR_VERSION: 'fixture' },
    { CURSOR_PROJECT_DIR: '/fixture/project', CLAUDECODE: '1' },
  ]) {
    it(`leaves reporting to hooks for ${Object.keys(markers).join(', ')}`, async () => {
      const p = project();
      try {
        const cli = await invoke(p, { markers, keepStdinOpen: true });
        assert.deepEqual(cli.bodies, []);
        assert.equal(existsSync(p.snapshot), false);
        assert.equal(existsSync(join(p.run, '.telemetry-lock')), false);
        assert.equal(existsSync(join(p.root, 'plugin-data')), false);
        const hook = await invoke(p, { emitter: HOOK, args: ['--reconcile'], markers });
        assert.deepEqual(hook.bodies.map(activity).map((a) => a.eventName), ['RUN_STARTED']);
        assert.equal(hook.bodies[0].source, markers.CURSOR_VERSION || markers.CURSOR_PROJECT_DIR ? 'CURSOR' : 'CLAUDE_CODE');
        assert.equal(readSnapshot(p).via, 'hook');
      } finally { cleanup(p); }
    });
  }

  it('keeps consent grant and revoke available on hook hosts without reporting', async () => {
    const p = project('GCP_TO_AWS', null);
    try {
      for (const markers of [{ CLAUDECODE: '1' }, { CURSOR_VERSION: 'fixture' }]) {
        assert.equal((await invoke(p, { args: ['consent', 'grant'], markers })).stdout, 'granted\n');
        assert.equal((await invoke(p, { args: ['consent', 'get'], markers })).stdout, 'granted\n');
        assert.equal((await invoke(p, { args: ['consent', 'revoke'], markers })).stdout, 'revoked\n');
        assert.equal((await invoke(p, { args: ['consent', 'get'], markers })).stdout, 'revoked\n');
      }
      assert.equal(existsSync(p.snapshot), false);
    } finally { cleanup(p); }
  });

  it('does not wait for stdin and reconciles init, phase completion, decision-only completion and resume', async () => {
    const p = project();
    try {
      const initial = await invoke(p, { keepStdinOpen: true });
      assert.deepEqual(initial.bodies.map(activity).map((a) => a.eventName), ['RUN_STARTED']);
      assert.equal(initial.bodies[0].source, 'OTHER');
      assert.equal(activity(initial.bodies[0]).sessionId, undefined);
      p.state.phases.discover = 'completed'; p.state.current_phase = 'clarify'; save(p);
      const phase = await invoke(p);
      assert.deepEqual(phase.bodies.map(activity).map((a) => [a.eventName, a.phase]), [['PHASE_COMPLETED', 'DISCOVER']]);
      p.state.phases.clarify = 'completed'; p.state.current_phase = 'complete';
      Object.assign(p.state, { run_mode: 'decide' }); save(p);
      const terminal = (await invoke(p)).bodies.map(activity);
      assert.equal(terminal.find((a) => a.eventName === 'RUN_COMPLETED').attributes.runMode, 'DECIDE');
      assert.deepEqual((await invoke(p, { cwd: p.run })).bodies, []);
      assert.equal(readSnapshot(p).via, 'cli');
      assert.equal(readSnapshot(p).runId, RUN_ID);
    } finally { cleanup(p); }
  });
});

describe('standalone telemetry distributions', () => {
  for (const plugin of PLUGINS) {
    for (const [skill, owner] of [
      ['gcp-to-aws', 'GCP_TO_AWS'], ['heroku-to-aws', 'HEROKU_TO_AWS'], ['llm-to-bedrock', 'LLM_TO_BEDROCK'],
    ]) {
      it(`${plugin}/${skill} supplies the emitter and its own distribution version`, async () => {
        const p = project(owner);
        try {
          const telemetry = join(REPO, plugin, 'skills', skill, 'references/vendored/telemetry');
          const version = JSON.parse(readFileSync(join(REPO, plugin, '.claude-plugin/plugin.json'), 'utf8')).version;
          assert.ok(existsSync(join(telemetry, 'PROTOCOL.md')));
          const bodies = (await invoke(p, { emitter: join(telemetry, 'emit.mjs') })).bodies;
          assert.equal(bodies.length, 1);
          assert.equal(bodies[0].pluginVersion, version);
          assert.equal(activity(bodies[0]).skill, owner);
          assert.equal(bodies[0].source, 'OTHER');
        } finally { cleanup(p); }
      });
    }
  }
});

describe('CLI consent and reconciliation', () => {
  for (const location of ['plugin-data', '.aws-startups-plugins']) {
    it(`revokes and re-grants the effective ${location} consent for both CLI and hooks`, async () => {
      const p = project();
      try {
        const directory = join(p.root, location);
        mkdirSync(directory, { recursive: true });
        const file = join(directory, 'telemetry.json');
        writeFileSync(file, JSON.stringify({
          consent: 'granted', installId: RUN_ID,
          consentedAt: new Date(Date.now() - 60_000).toISOString(), version: 1,
        }));
        const initial = (await invoke(p)).bodies;
        assert.equal(initial.length, 1);
        const before = readFileSync(p.snapshot, 'utf8');
        assert.equal((await invoke(p, { args: ['consent', 'revoke'] })).stdout, 'revoked\n');
        assert.equal((await invoke(p, { args: ['consent', 'get'] })).stdout, 'revoked\n');
        assert.equal(JSON.parse(readFileSync(file, 'utf8')).consent, 'revoked');
        assert.equal(JSON.parse(readFileSync(file, 'utf8')).installId, RUN_ID);
        assert.equal(JSON.parse((await invoke(p, { args: ['consent', 'status'] })).stdout).consentFile, file);
        p.state.phases.discover = 'completed'; save(p);
        assert.deepEqual((await invoke(p)).bodies, []);
        assert.deepEqual((await invoke(p, {
          emitter: HOOK, args: ['--reconcile'], markers: { CLAUDECODE: '1' },
        })).bodies, []);
        assert.equal(readFileSync(p.snapshot, 'utf8'), before);
        assert.equal((await invoke(p, { args: ['consent', 'grant'] })).stdout, 'granted\n');
        assert.equal((await invoke(p, { args: ['consent', 'get'] })).stdout, 'granted\n');
        const resumed = (await invoke(p)).bodies;
        assert.deepEqual(resumed.map(activity).map((a) => [a.eventName, a.phase]), [
          ['PHASE_COMPLETED', 'DISCOVER'],
        ]);
        assert.equal(resumed[0].installId, initial[0].installId);
      } finally { cleanup(p); }
    });
  }

  it('updates the highest-priority consent record without overwriting another scope', async () => {
    const p = project();
    try {
      for (const location of ['plugin-data', '.aws-startups-plugins']) {
        const directory = join(p.root, location);
        mkdirSync(directory, { recursive: true });
        writeFileSync(join(directory, 'telemetry.json'), JSON.stringify({ consent: 'granted', installId: RUN_ID }));
      }
      const homeFile = join(p.root, '.aws-startups-plugins/telemetry.json');
      const homeBefore = readFileSync(homeFile, 'utf8');
      const projectBefore = readFileSync(p.consentFile, 'utf8');
      await invoke(p, { args: ['consent', 'revoke'] });
      assert.equal((await invoke(p, { args: ['consent', 'get'] })).stdout, 'revoked\n');
      assert.equal(readFileSync(homeFile, 'utf8'), homeBefore);
      assert.equal(readFileSync(p.consentFile, 'utf8'), projectBefore);
      assert.deepEqual((await invoke(p)).bodies, []);
    } finally { cleanup(p); }
  });

  it('can revoke an existing global decision outside a migration project without creating a project', async () => {
    const p = project();
    const outside = mkdtempSync(join(tmpdir(), 'telemetry-consent-outside-'));
    try {
      const directory = join(p.root, 'plugin-data');
      mkdirSync(directory);
      writeFileSync(join(directory, 'telemetry.json'), JSON.stringify({ consent: 'granted', installId: RUN_ID }));
      assert.equal((await invoke(p, { cwd: outside, args: ['consent', 'revoke'] })).stdout, 'revoked\n');
      assert.equal((await invoke(p, { cwd: outside, args: ['consent', 'get'] })).stdout, 'revoked\n');
      assert.equal(existsSync(join(outside, '.migration')), false);
    } finally { cleanup(p); rmSync(outside, { recursive: true, force: true }); }
  });

  it('does not create global consent when no decision or migration project exists', async () => {
    const p = project('GCP_TO_AWS', null);
    const outside = mkdtempSync(join(tmpdir(), 'telemetry-consent-outside-'));
    try {
      const result = await invoke(p, { cwd: outside, args: ['consent', 'grant'] });
      assert.equal(result.stdout, 'no .migration directory here; create the run first\n');
      assert.equal(existsSync(join(p.root, 'plugin-data')), false);
      assert.equal(existsSync(join(p.root, '.aws-startups-plugins')), false);
      assert.equal(existsSync(join(outside, '.migration')), false);
    } finally { cleanup(p); rmSync(outside, { recursive: true, force: true }); }
  });

  for (const consent of [null, 'revoked']) {
    it(`does not report with consent ${consent}`, async () => {
      const p = project('GCP_TO_AWS', consent);
      try {
        assert.deepEqual((await invoke(p)).bodies, []);
        assert.equal(existsSync(p.snapshot), false);
        assert.equal(existsSync(join(p.root, 'plugin-data')), false);
      } finally { cleanup(p); }
    });
  }

  it('honours opt-outs and a disabled endpoint without advancing snapshots', async () => {
    const p = project();
    try {
      for (const markers of [
        { DO_NOT_TRACK: '1' }, { AWS_STARTUP_ADVISOR_TELEMETRY: '0' }, { AWS_STARTUP_ADVISOR_TELEMETRY_ENDPOINT: '' },
      ]) {
        assert.deepEqual((await invoke(p, { markers })).bodies, []);
        assert.equal(existsSync(p.snapshot), false);
      }
    } finally { cleanup(p); }
  });

  it('reports a failed gate once and retains only a refused gate for replay', async () => {
    const p = project();
    try {
      writeFileSync(join(p.run, '.gate-failures.json'), JSON.stringify({ clarify: { reason: 'missing' } }));
      respondFor = (body) => activity(body).eventName === 'GATE_FAILED' ? 429 : 200;
      await invoke(p);
      assert.deepEqual(readSnapshot(p).gateFailures, []);
      respondFor = () => 200;
      const retry = (await invoke(p)).bodies.map(activity);
      assert.deepEqual(retry.map((a) => [a.eventName, a.phase, a.attributes.failureReason]), [
        ['GATE_FAILED', 'CLARIFY', 'MISSING'],
      ]);
      assert.deepEqual((await invoke(p)).bodies, []);
      p.state.phases.clarify = 'completed'; save(p);
      const passed = (await invoke(p)).bodies.map(activity);
      assert.deepEqual(passed.map((a) => [a.eventName, a.phase]), [['PHASE_COMPLETED', 'CLARIFY']]);
    } finally { respondFor = () => 200; cleanup(p); }
  });

  it('keeps a delegated run and a hidden Bedrock run distinct across resume', async () => {
    const p = project();
    try {
      Object.assign(p.state, { initiated_by: 'LLM_TO_BEDROCK' }); save(p);
      const bedrock = join(p.root, '.migration', '.bedrock-test-run');
      mkdirSync(bedrock);
      const state = {
        migration_id: '.bedrock-test-run', run_id: '19d61988-71f5-416e-a1a4-36e84a64ef18',
        owning_skill: 'LLM_TO_BEDROCK', current_phase: 'execute',
        phases: { assess: 'completed', execute: 'in_progress' },
      };
      const file = join(bedrock, '.phase-status.json');
      writeFileSync(file, JSON.stringify(state));
      const initial = (await invoke(p)).bodies.map(activity);
      assert.equal(initial.length, 2);
      assert.equal(initial.find((a) => a.skill === 'GCP_TO_AWS').initiatingSkill, 'LLM_TO_BEDROCK');
      assert.equal(initial.find((a) => a.skill === 'LLM_TO_BEDROCK').runId, state.run_id);
      assert.deepEqual((await invoke(p)).bodies, []);
      state.current_phase = 'complete'; state.phases.execute = 'completed';
      writeFileSync(file, JSON.stringify(state));
      const terminal = (await invoke(p)).bodies.map(activity);
      assert.deepEqual(terminal.map((a) => [a.eventName, a.skill]), [['RUN_COMPLETED', 'LLM_TO_BEDROCK']]);
    } finally { cleanup(p); }
  });

  it('shares a lock across duplicate CLI calls', async () => {
    const p = project();
    try {
      const start = received.length;
      await Promise.all([invoke(p), invoke(p), invoke(p)]);
      assert.equal(received.slice(start).filter((b) => activity(b).eventName === 'RUN_STARTED').length, 1);
      assert.equal(existsSync(join(p.run, '.telemetry-lock')), false);
    } finally { cleanup(p); }
  });
});
