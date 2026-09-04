// Contract tests use a small draft-07 subset validator to avoid a runtime dependency.
// Run: node --test tests/tools/application-source-contract.test.ts

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { describe, it } from 'node:test';

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type JsonObject = { [key: string]: Json };

const repoRoot = resolve(dirname(resolve(process.argv[1])), '../../../../..');
const migratePath = resolve(
  repoRoot,
  'migrate/plugins/migration-to-aws/skills/heroku-to-aws/references/shared/application-source-contract.schema.json',
);
const advisorPath = resolve(
  repoRoot,
  'advisor/plugins/aws-startup-advisor/skills/heroku-to-aws/references/shared/application-source-contract.schema.json',
);
const migrateProsePath = migratePath.replace('.schema.json', '.md');
const advisorProsePath = advisorPath.replace('.schema.json', '.md');
const migrateSchemaText = readFileSync(migratePath, 'utf8');
const schema = JSON.parse(migrateSchemaText) as JsonObject;

function object(value: Json): JsonObject {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) throw new Error('expected object');
  return value;
}

function resolveRef(ref: string): JsonObject {
  assert.match(ref, /^#\//);
  let current: Json = schema;
  for (const segment of ref.slice(2).split('/')) current = object(current)[segment];
  return object(current);
}

function same(left: Json, right: Json): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function assertJsonEqual(actual: Json, expected: Json): void {
  assert.equal(JSON.stringify(actual), JSON.stringify(expected));
}

function validate(node: JsonObject, value: Json, path = '$'): string[] {
  if (typeof node.$ref === 'string') return validate(resolveRef(node.$ref), value, path);
  const errors: string[] = [];

  if (Array.isArray(node.allOf)) {
    for (const part of node.allOf) errors.push(...validate(object(part), value, path));
  }
  if (Array.isArray(node.oneOf)) {
    const matches = node.oneOf.filter((part) => validate(object(part), value, path).length === 0);
    if (matches.length !== 1) errors.push(`${path}: expected exactly one oneOf match, got ${matches.length}`);
  }
  if (node.not && validate(object(node.not), value, path).length === 0) errors.push(`${path}: matched forbidden schema`);
  if (node.if) {
    const branch = validate(object(node.if), value, path).length === 0 ? node.then : node.else;
    if (branch) errors.push(...validate(object(branch), value, path));
  }
  if ('const' in node && !same(node.const, value)) errors.push(`${path}: does not match const`);
  if (Array.isArray(node.enum) && !node.enum.some((entry) => same(entry, value))) {
    errors.push(`${path}: is not in enum`);
  }

  const type = node.type;
  const typeMatches = type === undefined
    || (type === 'null' && value === null)
    || (type === 'boolean' && typeof value === 'boolean')
    || (type === 'number' && typeof value === 'number')
    || (type === 'integer' && typeof value === 'number' && Number.isInteger(value))
    || (type === 'string' && typeof value === 'string')
    || (type === 'array' && Array.isArray(value))
    || (type === 'object' && value !== null && typeof value === 'object' && !Array.isArray(value));
  if (!typeMatches) {
    errors.push(`${path}: expected ${String(type)}`);
    return errors;
  }

  if (typeof value === 'string') {
    if (typeof node.minLength === 'number' && value.length < node.minLength) errors.push(`${path}: too short`);
    if (typeof node.maxLength === 'number' && value.length > node.maxLength) errors.push(`${path}: too long`);
    if (typeof node.pattern === 'string' && !new RegExp(node.pattern, 'u').test(value)) {
      errors.push(`${path}: pattern mismatch`);
    }
  }
  if (typeof value === 'number') {
    if (typeof node.minimum === 'number' && value < node.minimum) errors.push(`${path}: below minimum`);
    if (typeof node.maximum === 'number' && value > node.maximum) errors.push(`${path}: above maximum`);
  }
  if (Array.isArray(value)) {
    if (typeof node.minItems === 'number' && value.length < node.minItems) errors.push(`${path}: too few items`);
    if (typeof node.maxItems === 'number' && value.length > node.maxItems) errors.push(`${path}: too many items`);
    if (node.uniqueItems === true && new Set(value.map((entry) => JSON.stringify(entry))).size !== value.length) {
      errors.push(`${path}: duplicate items`);
    }
    if (node.items) value.forEach((entry, index) => errors.push(...validate(object(node.items), entry, `${path}[${index}]`)));
  }
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    const properties = node.properties ? object(node.properties) : {};
    if (Array.isArray(node.required)) {
      for (const key of node.required) {
        if (typeof key === 'string' && !(key in value)) errors.push(`${path}: missing ${key}`);
      }
    }
    if (node.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!(key in properties)) errors.push(`${path}: undeclared ${key}`);
      }
    }
    for (const [key, childSchema] of Object.entries(properties)) {
      if (key in value) errors.push(...validate(object(childSchema), value[key], `${path}.${key}`));
    }
  }
  return errors;
}

const questions = [
  'runtime_framework',
  'build_method',
  'build_time_settings',
  'process_commands',
  'runtime_settings',
  'network_listeners',
  'port_host_binding',
  'heroku_runtime_behavior',
  'native_dependencies',
  'release_setup_commands',
  'recurring_jobs',
  'health_routes',
  'local_file_writes',
  'network_protocols',
  'potential_private_endpoints',
  'logs_telemetry',
  'postgresql_extensions',
  'redis_usage',
  'external_services',
  'application_connections',
  'addon_usage',
  'webhooks',
] as const;

function request(selected: readonly string[] = questions): JsonObject {
  return {
    application: { app_id: 'app-primary', app_name: 'example-app' },
    requested_questions: [...selected],
    context: {
      process_types: ['web'],
      configuration_names: ['API_URL', 'DATABASE_URL', 'PORT', 'REDIS_URL', 'SIGNING_SECRET'],
      postgres_attachment_present: true,
      redis_attachment_present: true,
      addon_ids: ['addon-postgres'],
      private_space_present: true,
      selected_estate_application_ids: ['app-secondary'],
    },
  };
}

const values: Record<(typeof questions)[number], Json[]> = {
  runtime_framework: [{ component_id: 'component-api', root: '.', runtime: 'nodejs', runtime_version: '24', framework: 'express' }],
  build_method: [{ component_id: 'component-api', method: 'buildpack', authority_path: 'package.json', context_path: 'services/api' }],
  build_time_settings: [{ component_id: 'component-api', setting_name: 'API_URL', stage: 'build', required: true }],
  process_commands: [{
    process_id: 'process-web',
    component_id: 'component-api',
    type: 'web',
    name: 'web',
    command: 'node server.js',
    entrypoint: 'server.js',
  }],
  runtime_settings: [{
    component_id: 'component-api',
    process_ids: ['process-web'],
    setting_name: 'PORT',
    use: 'HTTP listener port',
    required: true,
    default_present: false,
    loaded_dynamically: false,
  }],
  network_listeners: [{
    listener_id: 'listener-http',
    component_id: 'component-api',
    process_id: 'process-web',
    transport: 'TCP',
    port_setting_name: 'PORT',
    default_port: 3000,
    intended_traffic: 'public',
  }],
  port_host_binding: [{
    listener_id: 'listener-http',
    host_setting_name: 'HOST',
    port_setting_name: 'PORT',
    fixed_host: '0.0.0.0',
    fixed_port: 3000,
    host_configurable: true,
    port_configurable: true,
    beyond_loopback: true,
  }],
  heroku_runtime_behavior: [{
    component_id: 'component-api',
    process_ids: ['process-web'],
    metadata_name: 'DYNO',
    use: 'Instance labeling',
    effect: 'Changes log labels',
  }],
  native_dependencies: [{
    component_id: 'component-api',
    kind: 'library',
    name: 'libvips',
    phase: 'runtime',
    process_ids: ['process-web'],
    os_constraints: ['linux'],
    architecture_constraints: ['amd64'],
  }],
  release_setup_commands: [{
    component_id: 'component-api',
    process_id: 'process-web',
    command: 'npm run migrate',
    timing: 'release',
    purpose: 'Apply database migrations',
  }],
  recurring_jobs: [{
    job_id: 'job-cleanup',
    component_id: 'component-api',
    process_ids: ['process-web'],
    name: 'cleanup',
    mechanism: 'scheduler',
    command: 'npm run cleanup',
    schedule: '0 2 * * *',
    coordination: 'single execution',
  }],
  health_routes: [{
    component_id: 'component-api',
    process_id: 'process-web',
    listener_id: 'listener-http',
    path: '/health',
    methods: ['GET'],
    success_statuses: [200],
    redirects: false,
    authentication: 'none',
    required_headers: [],
  }],
  local_file_writes: [{
    component_id: 'component-api',
    process_ids: ['process-web'],
    setting_name: 'UPLOAD_DIR',
    default_path: 'tmp/uploads',
    read_after_write: true,
    purpose: 'Temporary upload processing',
    required_lifetime: 'request',
    cross_instance_required: false,
  }],
  network_protocols: [{
    component_id: 'component-api',
    process_ids: ['process-web'],
    direction: 'INBOUND',
    listener_id: 'listener-http',
    transport: 'TCP',
    application_protocol: 'HTTP',
    port: 3000,
    application_managed_tls: false,
  }],
  potential_private_endpoints: [{
    component_id: 'component-api',
    process_ids: ['process-web'],
    reference_kind: 'DEPENDENCY',
    reference_id: 'dependency-payments',
    setting_name: 'API_URL',
    host_pattern: 'internal.example.com',
    protocol: 'HTTPS',
    port: 443,
  }],
  logs_telemetry: [{
    component_id: 'component-api',
    process_ids: ['process-web'],
    signal: 'LOG',
    destination: 'stdout',
    setting_name: 'LOG_LEVEL',
    file_path: 'logs/application.log',
  }],
  postgresql_extensions: [{
    component_id: 'component-api',
    database_setting_name: 'DATABASE_URL',
    extension: 'pg_trgm',
    declaration_kind: 'migration',
    action: 'verify compatibility',
  }],
  redis_usage: [{
    component_id: 'component-api',
    setting_name: 'REDIS_URL',
    roles: ['cache'],
    disposability: 'DISPOSABLE',
  }],
  external_services: [{
    dependency_id: 'dependency-payments',
    component_id: 'component-api',
    process_ids: ['process-web'],
    direction: 'OUTBOUND',
    category: 'payments',
    service_reference: 'payment-api',
    setting_name: 'API_URL',
    role: 'Create charges',
    protocol: 'HTTPS',
    port: 443,
    authentication_mechanism: 'bearer token',
    allowlist_behavior: 'fixed egress required',
  }],
  application_connections: [{
    relationship_id: 'relationship-worker',
    caller_component_id: 'component-api',
    caller_process_ids: ['process-web'],
    callee_application_id: 'app-secondary',
    setting_name: 'WORKER_URL',
    protocol: 'HTTPS',
    ports: [443],
    mechanism: 'HTTP API',
  }],
  addon_usage: [{
    inventory_addon_id: 'addon-postgres',
    component_id: 'component-api',
    setting_name: 'DATABASE_URL',
    usage: 'RETAINED_EXTERNAL',
    roles: ['primary database'],
  }],
  webhooks: [{
    component_id: 'component-api',
    process_id: 'process-web',
    listener_id: 'listener-http',
    path: '/webhooks/payments',
    methods: ['POST'],
    provider_reference: 'payment provider',
    verification_mechanism: 'HMAC',
    verification_setting_name: 'SIGNING_SECRET',
    required_headers: ['X-Signature'],
  }],
};

function presentFindings(selected: readonly (typeof questions)[number][] = questions): JsonObject {
  return {
    findings: selected.map((question, index) => ({
      question,
      status: 'PRESENT',
      value: values[question],
      sources: index === 0 ? [{ path: 'package.json', line_start: 1, line_end: 8 }] : [],
      limitations: [],
    })),
  };
}

function recordsByQuestion(findings: JsonObject): Map<string, JsonObject[]> {
  const result = new Map<string, JsonObject[]>();
  for (const rawFinding of findings.findings as Json[]) {
    const finding = object(rawFinding);
    result.set(finding.question as string, Array.isArray(finding.value) ? finding.value.map(object) : []);
  }
  return result;
}

function validateSemantics(reviewRequest: JsonObject, answer: JsonObject): string[] {
  const errors: string[] = [];
  const requested = reviewRequest.requested_questions as string[];
  const requestedSet = new Set(requested);
  const rawFindings = answer.findings as Json[];
  const findingNames = rawFindings.map((raw) => object(raw).question as string);
  for (const question of requested) {
    if (findingNames.filter((name) => name === question).length !== 1) errors.push(`expected one finding for ${question}`);
  }
  for (const question of findingNames) {
    if (!requested.includes(question)) errors.push(`unrequested finding ${question}`);
  }
  for (const raw of rawFindings) {
    const finding = object(raw);
    const limitations = finding.limitations as JsonObject[];
    if (finding.status === 'UNKNOWN' && limitations.length === 0) errors.push(`${String(finding.question)}: UNKNOWN needs a limitation`);
    if (
      finding.status === 'ABSENT_WITHIN_REVIEWED_SCOPE'
      && limitations.some((item) =>
        ['SKIPPED_SOURCE', 'UNREADABLE_SOURCE', 'TRUNCATED_SOURCE', 'DYNAMIC_SOURCE'].includes(item.kind as string)
      )
    ) errors.push(`${String(finding.question)}: absence has an incomplete scope`);
    for (const source of (finding.sources ?? []) as JsonObject[]) {
      if (
        typeof source.line_start === 'number'
        && typeof source.line_end === 'number'
        && source.line_end < source.line_start
      ) errors.push(`${String(finding.question)}: source line bounds are reversed`);
    }
  }

  const records = recordsByQuestion(answer);
  const ids = (question: string, key: string) => (records.get(question) ?? []).map((item) => item[key] as string);
  const componentIds = ids('runtime_framework', 'component_id');
  const processIds = ids('process_commands', 'process_id');
  const listenerIds = ids('network_listeners', 'listener_id');
  const dependencyIds = ids('external_services', 'dependency_id');
  const relationshipIds = ids('application_connections', 'relationship_id');
  const components = new Set(componentIds);
  const processes = new Set(processIds);
  const listeners = new Set(listenerIds);
  const dependencies = new Set(dependencyIds);
  const estateApps = new Set(object(reviewRequest.context).selected_estate_application_ids as string[]);
  const addons = new Set(object(reviewRequest.context).addon_ids as string[]);

  for (const [question, questionRecords] of records) {
    for (const record of questionRecords) {
      for (const key of ['component_id', 'caller_component_id']) {
        if (
          requestedSet.has('runtime_framework')
          && typeof record[key] === 'string'
          && !components.has(record[key])
        ) errors.push(`${question}: broken ${key}`);
      }
      for (const key of ['process_id', 'process_ids', 'caller_process_ids']) {
        const references = typeof record[key] === 'string' ? [record[key]] : (record[key] ?? []) as Json[];
        for (const reference of references) {
          if (
            requestedSet.has('process_commands')
            && typeof reference === 'string'
            && !processes.has(reference)
          ) errors.push(`${question}: broken ${key}`);
        }
      }
      if (
        requestedSet.has('network_listeners')
        && typeof record.listener_id === 'string'
        && !listeners.has(record.listener_id)
      ) errors.push(`${question}: broken listener_id`);
      if (typeof record.callee_application_id === 'string' && !estateApps.has(record.callee_application_id)) {
        errors.push(`${question}: broken callee_application_id`);
      }
      if (typeof record.inventory_addon_id === 'string' && !addons.has(record.inventory_addon_id)) {
        errors.push(`${question}: broken inventory_addon_id`);
      }
      if (
        requestedSet.has('external_services')
        && record.reference_kind === 'DEPENDENCY'
        && !dependencies.has(record.reference_id as string)
      ) {
        errors.push(`${question}: broken dependency reference_id`);
      }
      if (record.reference_kind === 'APPLICATION' && !estateApps.has(record.reference_id as string)) {
        errors.push(`${question}: broken application reference_id`);
      }
    }
  }

  for (const [label, valuesToCheck] of [
    ['component', componentIds],
    ['process', processIds],
    ['listener', listenerIds],
    ['dependency', dependencyIds],
    ['relationship', relationshipIds],
  ] as const) {
    if (new Set(valuesToCheck).size !== valuesToCheck.length) errors.push(`duplicate ${label} id`);
  }
  return errors;
}

function clone<T extends Json>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

describe('application-source contract', () => {
  it('keeps plugin copies synchronized and declares all approved questions', () => {
    assert.equal(readFileSync(advisorPath, 'utf8'), migrateSchemaText);
    assert.equal(readFileSync(advisorProsePath, 'utf8'), readFileSync(migrateProsePath, 'utf8'));
    assertJsonEqual(object(object(schema.definitions).question).enum, [...questions]);
  });

  it('accepts a request and resolvable PRESENT findings covering all questions', () => {
    const reviewRequest = request();
    const answer = presentFindings();
    assertJsonEqual(validate(schema, reviewRequest), []);
    assertJsonEqual(validate(schema, answer), []);
    assertJsonEqual(validateSemantics(reviewRequest, answer), []);
  });

  it('accepts bounded non-present statuses and requires a limitation for UNKNOWN', () => {
    const reviewRequest = request(['runtime_framework', 'build_method', 'build_time_settings']);
    const answer: JsonObject = {
      findings: [
        { question: 'runtime_framework', status: 'ABSENT_WITHIN_REVIEWED_SCOPE', value: null, limitations: [] },
        {
          question: 'build_method',
          status: 'UNKNOWN',
          value: null,
          limitations: [{ kind: 'UNREADABLE_SOURCE', detail: 'Build manifest could not be read.' }],
        },
        { question: 'build_time_settings', status: 'NOT_APPLICABLE', value: null, limitations: [] },
      ],
    };
    assertJsonEqual(validate(schema, answer), []);
    assertJsonEqual(validateSemantics(reviewRequest, answer), []);
    (object((answer.findings as Json[])[1]).limitations as Json[]) = [];
    assert.ok(validate(schema, answer).length > 0);
    assert.match(validateSemantics(reviewRequest, answer).join('\n'), /UNKNOWN needs a limitation/);
  });

  it('rejects undeclared, value-bearing, malformed, and unbounded request data', () => {
    for (const mutate of [
      (sample: JsonObject) => sample.secret = 'no',
      (sample: JsonObject) => object(sample.context).configuration_values = { API_URL: 'secret' },
      (sample: JsonObject) => object(sample.context).credentials = ['token'],
      (sample: JsonObject) => object(sample.application).app_name = '',
      (sample: JsonObject) => object(sample.application).app_name = 'x'.repeat(129),
      (sample: JsonObject) => (sample.requested_questions as Json[]).push('runtime_framework'),
      (sample: JsonObject) => (sample.requested_questions as Json[])[0] = 'not_a_question',
    ]) {
      const sample = request();
      mutate(sample);
      assert.ok(validate(schema, sample).length > 0);
    }
  });

  it('rejects malformed findings, values, and source locations', () => {
    const base = presentFindings(['network_listeners']);
    const finding = () => object((clone(base).findings as Json[])[0]);
    for (const sample of [
      Object.assign(finding(), { extra: true }),
      Object.assign(finding(), { status: 'MAYBE' }),
      Object.assign(finding(), { value: null }),
      Object.assign(finding(), { status: 'NOT_APPLICABLE' }),
      Object.assign(finding(), { limitations: [{ kind: 'OTHER', detail: '' }] }),
      Object.assign(finding(), {
        value: [{ ...object(values.network_listeners[0]), default_port: 70000 }],
      }),
    ]) {
      assert.ok(validate(schema, { findings: [sample] }).length > 0);
    }
    for (
      const path of [
        '/etc/passwd',
        'C:/secret',
        'C:secret',
        '.',
        'src/./secret',
        '..',
        '../secret',
        'src/../secret',
        'src//secret',
        String.raw`src\secret`,
        ' /etc/passwd',
        '\t/etc/passwd',
        ' ..',
        ' ./secret',
        ' C:/secret',
        'src/ ../secret',
        '~/.ssh/id_rsa',
        'src/file.js ',
      ]
    ) {
      const sample = finding();
      sample.sources = [{ path }];
      assert.ok(validate(schema, { findings: [sample] }).length > 0, path);
    }
    const pathWithInternalSpace = finding();
    pathWithInternalSpace.sources = [{ path: 'src/My File.js' }];
    assertJsonEqual(validate(schema, { findings: [pathWithInternalSpace] }), []);
  });

  it('rejects duplicate, missing, and unrequested findings', () => {
    const reviewRequest = request(['runtime_framework']);
    const answer = presentFindings(['runtime_framework']);
    (answer.findings as Json[]).push(clone((answer.findings as Json[])[0]));
    assert.match(validateSemantics(reviewRequest, answer).join('\n'), /expected one finding/);
    (answer.findings as Json[]) = [];
    assert.match(validateSemantics(reviewRequest, answer).join('\n'), /expected one finding/);
    const unrequested = presentFindings(['build_method']);
    assert.match(validateSemantics(reviewRequest, unrequested).join('\n'), /unrequested finding/);

    const duplicateId = presentFindings();
    const runtimeValue = object((duplicateId.findings as Json[])[0]).value as Json[];
    runtimeValue.push(clone(runtimeValue[0]));
    assert.match(validateSemantics(request(), duplicateId).join('\n'), /duplicate component id/);
  });

  it('accepts partial requests when the defining question was not requested', () => {
    for (const question of [
      'process_commands',
      'network_listeners',
      'health_routes',
      'potential_private_endpoints',
    ] as const) {
      const reviewRequest = request([question]);
      const answer = presentFindings([question]);
      assertJsonEqual(validate(schema, answer), []);
      assertJsonEqual(validateSemantics(reviewRequest, answer), []);
    }
  });

  it('retains source names that are absent from Heroku inventory context', () => {
    const selected = [
      'process_commands',
      'port_host_binding',
      'logs_telemetry',
      'local_file_writes',
      'application_connections',
    ] as const;
    const reviewRequest = request(selected);
    const answer = presentFindings(selected);
    const processFinding = (answer.findings as Json[]).map(object).find((item) =>
      item.question === 'process_commands'
    );
    if (!processFinding || !Array.isArray(processFinding.value)) throw new Error('missing process_commands');
    object(processFinding.value[0]).type = 'worker';

    assertJsonEqual(validate(schema, answer), []);
    assertJsonEqual(validateSemantics(reviewRequest, answer), []);
  });

  it('rejects qualified absence and reversed line bounds', () => {
    const reviewRequest = request(['runtime_framework']);
    const answer: JsonObject = {
      findings: [{
        question: 'runtime_framework',
        status: 'ABSENT_WITHIN_REVIEWED_SCOPE',
        value: null,
        sources: [{ path: 'package.json', line_start: 8, line_end: 1 }],
        limitations: [{ kind: 'TRUNCATED_SOURCE', detail: 'The manifest exceeded the review limit.' }],
      }],
    };
    assert.match(validateSemantics(reviewRequest, answer).join('\n'), /incomplete scope/);
    assert.match(validateSemantics(reviewRequest, answer).join('\n'), /line bounds are reversed/);
  });

  it('rejects broken shared references', () => {
    for (const [question, key] of [
      ['build_method', 'component_id'],
      ['network_listeners', 'process_id'],
      ['health_routes', 'listener_id'],
      ['potential_private_endpoints', 'reference_id'],
      ['application_connections', 'callee_application_id'],
      ['addon_usage', 'inventory_addon_id'],
    ] as const) {
      const answer = presentFindings();
      const finding = (answer.findings as Json[]).map(object).find((item) => item.question === question);
      if (!finding || !Array.isArray(finding.value)) throw new Error(`missing value for ${question}`);
      object(finding.value[0])[key] = 'missing-id';
      assert.ok(validateSemantics(request(), answer).length > 0, `${question}.${key}`);
    }
  });
});
