// Feature: heroku-to-aws-migration
// Property-based tests for Discovery phase logic (Properties 2-5, 12)
//
// Run: node --test tests/property/heroku/discovery.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

// --- Implementation: Procfile Parser (Property 2) ---

function parseProcfile(content) {
  if (!content || content.trim() === '') return {};
  const entries = {};
  const lines = content.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '' || trimmed.startsWith('#')) continue;
    const colonIdx = trimmed.indexOf(':');
    if (colonIdx === -1) continue;
    const processType = trimmed.slice(0, colonIdx).trim();
    const command = trimmed.slice(colonIdx + 1).trim();
    if (processType && command) {
      entries[processType] = command;
    }
  }
  return entries;
}

function serializeProcfile(entries) {
  return Object.entries(entries)
    .map(([type, cmd]) => `${type}: ${cmd}`)
    .join('\n');
}

// --- Implementation: app.json Extractor (Property 3) ---

function extractAppJson(manifest) {
  const result = {};
  if (manifest.addons) result.addons = manifest.addons;
  if (manifest.env) result.env = manifest.env;
  if (manifest.formation) result.formation = manifest.formation;
  if (manifest.buildpacks) result.buildpacks = manifest.buildpacks;
  if (manifest.name) result.name = manifest.name;
  if (manifest.description) result.description = manifest.description;
  if (manifest.stack) result.stack = manifest.stack;
  if (manifest.scripts) result.scripts = manifest.scripts;
  return result;
}

// --- Implementation: Inventory Schema Validator (Property 4) ---

function buildInventory(apps, resources, sources) {
  return {
    metadata: {
      discovery_timestamp: new Date().toISOString(),
      total_apps_discovered: apps.length,
      discovery_sources: sources,
      confidence: sources.includes('terraform') ? 'full' : 'reduced',
    },
    apps: apps.map(app => ({
      app_name: app.name,
      app_id: app.id,
      heroku_generation: app.generation || 'cedar',
      discovery_status: app.status || 'success',
    })),
    resources: resources.map(r => ({
      resource_id: r.resource_id,
      resource_type: r.resource_type,
      heroku_app: r.heroku_app,
      config: r.config,
    })),
  };
}

function validateInventory(inventory) {
  const errors = [];
  if (!inventory.metadata) errors.push('missing metadata');
  else {
    if (!inventory.metadata.discovery_timestamp) errors.push('missing discovery_timestamp');
    if (typeof inventory.metadata.total_apps_discovered !== 'number') errors.push('missing total_apps_discovered');
  }
  if (!Array.isArray(inventory.resources)) errors.push('resources is not an array');
  else {
    for (const r of inventory.resources) {
      if (!r.resource_id) errors.push(`resource missing resource_id`);
      if (!r.resource_type) errors.push(`resource missing resource_type`);
      if (!r.heroku_app) errors.push(`resource missing heroku_app`);
      if (!r.config) errors.push(`resource missing config`);
    }
  }
  return errors;
}

// --- Implementation: Terraform Authoritative Source (Property 5) ---

function extractTerraformValue(terraformValue, field) {
  return {
    resolved_value: terraformValue,
    source: {
      field,
      value: terraformValue,
      origin: 'terraform',
    },
  };
}

// --- Implementation: Flat Resource Model (Property 12) ---

const CLUSTERING_FIELDS = ['cluster_id', 'creation_order_depth', 'edges', 'dependencies', 'must_migrate_together'];

function buildFlatResourceList(resources) {
  return resources.map(r => ({
    resource_id: r.resource_id,
    resource_type: r.resource_type,
    heroku_app: r.heroku_app,
    config: r.config,
  }));
}

// --- Generators ---

const arbProcessType = fc.stringOf(
  fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz_'),
  { minLength: 1, maxLength: 15 }
).filter(s => /^[a-z][a-z_]*$/.test(s));

const arbCommand = fc.stringOf(
  fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789 -./'),
  { minLength: 3, maxLength: 60 }
).filter(s => s.trim().length >= 3 && !s.includes('\n') && !s.includes(':'))
  .map(s => s.trim());

const arbProcfileEntries = fc.dictionary(arbProcessType, arbCommand, { minKeys: 1, maxKeys: 8 });

const arbAddon = fc.record({
  plan: fc.constantFrom('hobby', 'standard-0', 'premium-0', 'enterprise'),
  url: fc.constant('postgres://host/db'),
});

const arbEnvVar = fc.record({
  description: fc.string({ minLength: 1, maxLength: 50 }),
  required: fc.boolean(),
});

const arbFormation = fc.record({
  quantity: fc.integer({ min: 1, max: 10 }),
  size: fc.constantFrom('standard-1x', 'standard-2x', 'performance-m'),
});

const arbBuildpack = fc.record({
  url: fc.constantFrom(
    'heroku/nodejs',
    'heroku/python',
    'heroku/ruby',
    'heroku/java',
    'heroku/go'
  ),
});

const arbAppJson = fc.record({
  name: fc.string({ minLength: 1, maxLength: 30 }),
  description: fc.string({ minLength: 0, maxLength: 100 }),
  stack: fc.constantFrom('heroku-22', 'heroku-24'),
  addons: fc.array(fc.constantFrom('heroku-postgresql', 'heroku-redis', 'papertrail'), { minLength: 0, maxLength: 5 }),
  env: fc.dictionary(
    fc.stringOf(fc.constantFrom(...'ABCDEFGHIJKLMNOPQRSTUVWXYZ_'), { minLength: 1, maxLength: 20 }),
    arbEnvVar,
    { minKeys: 0, maxKeys: 5 }
  ),
  formation: fc.dictionary(arbProcessType, arbFormation, { minKeys: 0, maxKeys: 3 }),
  buildpacks: fc.array(arbBuildpack, { minLength: 0, maxLength: 3 }),
  scripts: fc.record({
    postdeploy: fc.constantFrom('node setup.js', 'rake db:migrate', undefined),
  }),
});

const arbResourceType = fc.constantFrom('formation', 'addon', 'space', 'pipeline');

const arbAppName = fc.stringOf(
  fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789-'),
  { minLength: 3, maxLength: 20 }
).filter(s => /^[a-z]/.test(s));

const arbResource = fc.record({
  resource_id: fc.string({ minLength: 5, maxLength: 40 }),
  resource_type: arbResourceType,
  heroku_app: arbAppName,
  config: fc.record({
    plan: fc.constantFrom('standard-0', 'premium-0', 'hobby'),
  }),
});

const arbApp = fc.record({
  name: arbAppName,
  id: fc.uuid(),
  generation: fc.constantFrom('cedar', 'fir', 'unknown'),
  status: fc.constantFrom('success', 'discovery_failed'),
});

const arbDiscoverySources = fc.subarray(
  ['terraform', 'procfile', 'billing'],
  { minLength: 1 }
);

// --- Property Tests ---

describe('Feature: heroku-to-aws-migration, Property 2: Procfile parsing extracts all process types', () => {
  it('extracted entries reproduce an equivalent Procfile', () => {
    fc.assert(fc.property(arbProcfileEntries, (entries) => {
      const procfileContent = serializeProcfile(entries);
      const parsed = parseProcfile(procfileContent);

      // Every original entry should be extracted
      for (const [type, cmd] of Object.entries(entries)) {
        assert.ok(type in parsed, `Missing process type: ${type}`);
        assert.equal(parsed[type], cmd);
      }

      // No extra entries
      assert.equal(Object.keys(parsed).length, Object.keys(entries).length);
    }), { numRuns: 100 });
  });

  it('handles comments and blank lines without extracting them', () => {
    fc.assert(fc.property(
      arbProcfileEntries,
      fc.array(fc.constantFrom('# comment line', '  ', '', '## another comment'), { minLength: 0, maxLength: 3 }),
      (entries, noise) => {
        const lines = [
          ...noise,
          ...Object.entries(entries).map(([t, c]) => `${t}: ${c}`),
          ...noise,
        ];
        const content = lines.join('\n');
        const parsed = parseProcfile(content);

        assert.equal(Object.keys(parsed).length, Object.keys(entries).length);
      }
    ), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 3: app.json extraction completeness', () => {
  it('extracts all declared sections with correct values', () => {
    fc.assert(fc.property(arbAppJson, (manifest) => {
      const extracted = extractAppJson(manifest);

      // Every section present in manifest should be present in extraction
      if (manifest.addons) assert.deepEqual(extracted.addons, manifest.addons);
      if (manifest.env) assert.deepEqual(extracted.env, manifest.env);
      if (manifest.formation) assert.deepEqual(extracted.formation, manifest.formation);
      if (manifest.buildpacks) assert.deepEqual(extracted.buildpacks, manifest.buildpacks);
      if (manifest.name) assert.equal(extracted.name, manifest.name);
      if (manifest.description) assert.equal(extracted.description, manifest.description);
      if (manifest.stack) assert.equal(extracted.stack, manifest.stack);
      if (manifest.scripts) assert.deepEqual(extracted.scripts, manifest.scripts);
    }), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 4: Inventory schema conformance', () => {
  it('produced inventory has metadata and required resource fields', () => {
    fc.assert(fc.property(
      fc.array(arbApp, { minLength: 1, maxLength: 5 }),
      fc.array(arbResource, { minLength: 1, maxLength: 10 }),
      arbDiscoverySources,
      (apps, resources, sources) => {
        const inventory = buildInventory(apps, resources, sources);
        const errors = validateInventory(inventory);

        assert.equal(errors.length, 0, `Validation errors: ${errors.join(', ')}`);
        assert.equal(inventory.metadata.total_apps_discovered, apps.length);
        assert.ok(inventory.metadata.discovery_timestamp);
        assert.ok(Array.isArray(inventory.metadata.discovery_sources));
      }
    ), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 5: Terraform is authoritative source', () => {
  it('resolved value is always the Terraform value', () => {
    fc.assert(fc.property(
      fc.oneof(fc.integer(), fc.string({ minLength: 1, maxLength: 50 })),
      fc.string({ minLength: 1, maxLength: 30 }),
      (terraformValue, field) => {
        const result = extractTerraformValue(terraformValue, field);

        assert.equal(result.resolved_value, terraformValue);
        assert.equal(result.source.value, terraformValue);
        assert.equal(result.source.origin, 'terraform');
      }
    ), { numRuns: 100 });
  });

  it('source metadata records field and origin', () => {
    fc.assert(fc.property(
      fc.integer({ min: 1, max: 100 }),
      (tfVal) => {
        const result = extractTerraformValue(tfVal, 'formation.quantity');
        assert.notEqual(result.source.value, undefined);
        assert.equal(result.source.field, 'formation.quantity');
        assert.equal(result.source.origin, 'terraform');
      }
    ), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 12: Flat resource model invariant', () => {
  it('no clustering fields present in output', () => {
    fc.assert(fc.property(
      fc.array(arbResource, { minLength: 1, maxLength: 15 }),
      (resources) => {
        const flat = buildFlatResourceList(resources);
        for (const r of flat) {
          for (const field of CLUSTERING_FIELDS) {
            assert.equal(field in r, false, `Found clustering field: ${field}`);
          }
        }
      }
    ), { numRuns: 100 });
  });

  it('input order is preserved', () => {
    fc.assert(fc.property(
      fc.array(arbResource, { minLength: 2, maxLength: 15 }),
      (resources) => {
        const flat = buildFlatResourceList(resources);
        assert.equal(flat.length, resources.length);
        for (let i = 0; i < resources.length; i++) {
          assert.equal(flat[i].resource_id, resources[i].resource_id);
        }
      }
    ), { numRuns: 100 });
  });

  it('resources sharing same heroku_app have identical heroku_app value', () => {
    fc.assert(fc.property(
      arbAppName,
      fc.array(arbResource, { minLength: 2, maxLength: 5 }),
      (appName, resources) => {
        const sameApp = resources.map(r => ({ ...r, heroku_app: appName }));
        const flat = buildFlatResourceList(sameApp);
        const appValues = new Set(flat.map(r => r.heroku_app));
        assert.equal(appValues.size, 1);
        assert.ok(appValues.has(appName));
      }
    ), { numRuns: 100 });
  });
});
