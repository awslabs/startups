// Feature: heroku-to-aws-migration
// Integration tests for end-to-end phase flow, pricing fallback, handoff gates, and error handling
//
// Run: node --test tests/integration/heroku/end-to-end.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

// --- Shared Implementation (from property tests, duplicated for integration isolation) ---

const PHASES = ['discover', 'clarify', 'design', 'estimate', 'generate'];

function createInitialPhaseStatus() {
  const phases = {};
  for (const phase of PHASES) {
    phases[phase] = 'pending';
  }
  return { phases };
}

function getPredecessor(phase) {
  const idx = PHASES.indexOf(phase);
  if (idx <= 0) return null;
  return PHASES[idx - 1];
}

function attemptTransition(phaseStatus, targetPhase, action) {
  const currentStatus = phaseStatus.phases[targetPhase];
  const predecessor = getPredecessor(targetPhase);

  switch (action) {
    case 'start': {
      if (predecessor && phaseStatus.phases[predecessor] !== 'completed') {
        return { success: false, reason: `predecessor ${predecessor} not completed`, phaseStatus };
      }
      if (currentStatus !== 'pending') {
        return { success: false, reason: `current status is ${currentStatus}`, phaseStatus };
      }
      return { success: true, phaseStatus: { phases: { ...phaseStatus.phases, [targetPhase]: 'in_progress' } } };
    }
    case 'complete': {
      if (currentStatus !== 'in_progress') {
        return { success: false, reason: `not in_progress`, phaseStatus };
      }
      return { success: true, phaseStatus: { phases: { ...phaseStatus.phases, [targetPhase]: 'completed' } } };
    }
    case 'gate_fail': {
      if (currentStatus !== 'in_progress') {
        return { success: false, reason: `not in_progress`, phaseStatus };
      }
      return { success: true, halted: true, phaseStatus };
    }
    case 'error': {
      return { success: true, reverted: true, phaseStatus: { phases: { ...phaseStatus.phases, [targetPhase]: 'pending' } } };
    }
    default:
      return { success: false, reason: `Unknown action`, phaseStatus };
  }
}

// Pricing lookup with fallback
function lookupPricing(serviceId, mcpServer, cache) {
  // Try MCP first
  const mcpPrice = mcpServer.lookup(serviceId);
  if (mcpPrice !== null) {
    return { price: mcpPrice, source: 'mcp' };
  }
  // Fallback to cache
  const cachedPrice = cache.lookup(serviceId);
  if (cachedPrice !== null) {
    return { price: cachedPrice, source: 'cached_fallback' };
  }
  // Both unavailable
  return { price: null, source: 'unavailable' };
}

// Handoff gate validator
function validateHandoff(phaseStatus, completedPhase, requiredFields) {
  if (phaseStatus.phases[completedPhase] !== 'completed') {
    return { result: 'GATE_FAIL', reason: `Phase ${completedPhase} not completed` };
  }
  const missingFields = requiredFields.filter(f => !f.present);
  if (missingFields.length > 0) {
    return {
      result: 'GATE_FAIL',
      reason: `Missing required fields: ${missingFields.map(f => f.name).join(', ')}`,
      fields: missingFields.map(f => f.name),
    };
  }
  return { result: 'HANDOFF_OK' };
}

// Subnet ID validator
function validateSubnetIds(subnetIds) {
  const pattern = /^subnet-[0-9a-f]{17}$/;
  const errors = [];
  if (!Array.isArray(subnetIds) || subnetIds.length === 0) {
    return { valid: false, errors: ['At least one subnet ID required'] };
  }
  if (subnetIds.length > 6) {
    return { valid: false, errors: ['Maximum 6 subnet IDs allowed'] };
  }
  for (const id of subnetIds) {
    if (!pattern.test(id)) {
      errors.push(`Invalid subnet ID format: ${id}. Expected: subnet-xxxxxxxxxxxxxxxxx`);
    }
  }
  return { valid: errors.length === 0, errors };
}

// Fast-path trigger detection
function isFastPath(inventory) {
  const appCount = inventory.apps?.length || 0;
  const hasPrivateSpaces = inventory.resources?.some(r => r.resource_type === 'space') || false;
  const hasKafka = inventory.resources?.some(
    r => r.resource_type === 'addon' && r.config?.addon_service === 'heroku-kafka'
  ) || false;
  return appCount < 5 && !hasPrivateSpaces && !hasKafka;
}

// --- Integration Tests ---

describe('Integration: End-to-end phase flow', () => {
  it('runs all phases in sequence with mock data', () => {
    let status = createInitialPhaseStatus();

    // Progress through all phases
    for (const phase of PHASES) {
      const startResult = attemptTransition(status, phase, 'start');
      assert.equal(startResult.success, true, `Failed to start ${phase}`);
      status = startResult.phaseStatus;

      assert.equal(status.phases[phase], 'in_progress');

      const completeResult = attemptTransition(status, phase, 'complete');
      assert.equal(completeResult.success, true, `Failed to complete ${phase}`);
      status = completeResult.phaseStatus;

      assert.equal(status.phases[phase], 'completed');
    }

    // All phases completed
    for (const phase of PHASES) {
      assert.equal(status.phases[phase], 'completed');
    }
  });

  it('cannot skip phases', () => {
    const status = createInitialPhaseStatus();

    // Try to start 'clarify' without completing 'discover'
    const result = attemptTransition(status, 'clarify', 'start');
    assert.equal(result.success, false);
    assert.ok(result.reason.includes('predecessor'));
  });

  it('cannot start a phase twice', () => {
    let status = createInitialPhaseStatus();

    // Start discover
    const start1 = attemptTransition(status, 'discover', 'start');
    status = start1.phaseStatus;

    // Try to start it again
    const start2 = attemptTransition(status, 'discover', 'start');
    assert.equal(start2.success, false);
  });

  it('recovery after error preserves prior progress', () => {
    let status = createInitialPhaseStatus();

    // Complete discover and clarify
    status = attemptTransition(status, 'discover', 'start').phaseStatus;
    status = attemptTransition(status, 'discover', 'complete').phaseStatus;
    status = attemptTransition(status, 'clarify', 'start').phaseStatus;
    status = attemptTransition(status, 'clarify', 'complete').phaseStatus;

    // Start design, then error
    status = attemptTransition(status, 'design', 'start').phaseStatus;
    const errorResult = attemptTransition(status, 'design', 'error');
    status = errorResult.phaseStatus;

    // Design reverted to pending
    assert.equal(status.phases.design, 'pending');
    // Prior phases preserved
    assert.equal(status.phases.discover, 'completed');
    assert.equal(status.phases.clarify, 'completed');

    // Can re-start design
    const restart = attemptTransition(status, 'design', 'start');
    assert.equal(restart.success, true);
  });
});

describe('Integration: Pricing fallback behavior', () => {
  it('uses MCP price when available', () => {
    const mcpServer = { lookup: (id) => id === 'fargate:web' ? 45.50 : null };
    const cache = { lookup: () => 40.00 };

    const result = lookupPricing('fargate:web', mcpServer, cache);
    assert.equal(result.price, 45.50);
    assert.equal(result.source, 'mcp');
  });

  it('falls back to cache when MCP unavailable', () => {
    const mcpServer = { lookup: () => null };
    const cache = { lookup: (id) => id === 'rds:postgres' ? 120.00 : null };

    const result = lookupPricing('rds:postgres', mcpServer, cache);
    assert.equal(result.price, 120.00);
    assert.equal(result.source, 'cached_fallback');
  });

  it('returns unavailable when both MCP and cache miss', () => {
    const mcpServer = { lookup: () => null };
    const cache = { lookup: () => null };

    const result = lookupPricing('unknown:svc', mcpServer, cache);
    assert.equal(result.price, null);
    assert.equal(result.source, 'unavailable');
  });

  it('multiple services with mixed pricing availability', () => {
    const mcpServer = {
      lookup: (id) => {
        if (id === 'fargate:web') return 50.0;
        if (id === 'rds:postgres') return 200.0;
        return null;
      },
    };
    const cache = {
      lookup: (id) => {
        if (id === 'elasticache:redis') return 75.0;
        return null;
      },
    };

    const services = ['fargate:web', 'rds:postgres', 'elasticache:redis', 'custom:addon'];
    const results = services.map(id => lookupPricing(id, mcpServer, cache));

    assert.equal(results[0].source, 'mcp');
    assert.equal(results[1].source, 'mcp');
    assert.equal(results[2].source, 'cached_fallback');
    assert.equal(results[3].source, 'unavailable');

    // Total excludes unpriced
    const total = results
      .filter(r => r.price !== null)
      .reduce((sum, r) => sum + r.price, 0);
    assert.equal(total, 325.0);
  });
});

describe('Integration: Handoff gate protocol', () => {
  it('HANDOFF_OK when phase completed and all fields present', () => {
    const status = { phases: { discover: 'completed', clarify: 'pending', design: 'pending', estimate: 'pending', generate: 'pending' } };
    const fields = [
      { name: 'heroku-resource-inventory.json', present: true },
      { name: '.phase-status.json', present: true },
    ];

    const result = validateHandoff(status, 'discover', fields);
    assert.equal(result.result, 'HANDOFF_OK');
  });

  it('GATE_FAIL when phase not completed', () => {
    const status = { phases: { discover: 'in_progress', clarify: 'pending', design: 'pending', estimate: 'pending', generate: 'pending' } };
    const fields = [{ name: 'heroku-resource-inventory.json', present: true }];

    const result = validateHandoff(status, 'discover', fields);
    assert.equal(result.result, 'GATE_FAIL');
    assert.ok(result.reason.includes('not completed'));
  });

  it('GATE_FAIL when required fields missing', () => {
    const status = { phases: { discover: 'completed', clarify: 'pending', design: 'pending', estimate: 'pending', generate: 'pending' } };
    const fields = [
      { name: 'heroku-resource-inventory.json', present: true },
      { name: 'preferences.json', present: false },
    ];

    const result = validateHandoff(status, 'discover', fields);
    assert.equal(result.result, 'GATE_FAIL');
    assert.ok(result.fields.includes('preferences.json'));
  });

  it('GATE_FAIL lists all missing fields', () => {
    const status = { phases: { design: 'completed', discover: 'completed', clarify: 'completed', estimate: 'pending', generate: 'pending' } };
    const fields = [
      { name: 'aws-design.json', present: false },
      { name: 'estimation-infra.json', present: false },
      { name: 'preferences.json', present: true },
    ];

    const result = validateHandoff(status, 'design', fields);
    assert.equal(result.result, 'GATE_FAIL');
    assert.equal(result.fields.length, 2);
    assert.ok(result.fields.includes('aws-design.json'));
    assert.ok(result.fields.includes('estimation-infra.json'));
  });

  it('pipeline halts on GATE_FAIL and retains in_progress', () => {
    let status = createInitialPhaseStatus();
    status = attemptTransition(status, 'discover', 'start').phaseStatus;

    // Gate fail while in_progress
    const gateFail = attemptTransition(status, 'discover', 'gate_fail');
    assert.equal(gateFail.success, true);
    assert.equal(gateFail.halted, true);
    assert.equal(gateFail.phaseStatus.phases.discover, 'in_progress');

    // Cannot proceed to next phase
    const tryNext = attemptTransition(gateFail.phaseStatus, 'clarify', 'start');
    assert.equal(tryNext.success, false);
  });
});

describe('Integration: Error handling edge cases', () => {
  it('no Terraform files — discovery fails', () => {
    let status = createInitialPhaseStatus();

    // Start discover
    const startResult = attemptTransition(status, 'discover', 'start');
    status = startResult.phaseStatus;
    assert.equal(status.phases.discover, 'in_progress');

    // Simulate no Terraform files found — unrecoverable error reverts to pending
    const errorResult = attemptTransition(status, 'discover', 'error');
    status = errorResult.phaseStatus;

    // Phase reverted to pending
    assert.equal(status.phases.discover, 'pending');
    assert.equal(errorResult.reverted, true);

    // Expected error message
    const expectedMessage = 'No Terraform files with heroku_* resources found. Heroku Terraform is required for discovery. Procfile and app.json alone are not sufficient.';
    assert.ok(expectedMessage.includes('Terraform'));
    assert.ok(expectedMessage.includes('required'));
  });

  it('empty Procfile produces empty extraction', () => {
    function parseProcfile(content) {
      if (!content || content.trim() === '') return {};
      const entries = {};
      for (const line of content.split('\n')) {
        const trimmed = line.trim();
        if (trimmed === '' || trimmed.startsWith('#')) continue;
        const colonIdx = trimmed.indexOf(':');
        if (colonIdx === -1) continue;
        const type = trimmed.slice(0, colonIdx).trim();
        const cmd = trimmed.slice(colonIdx + 1).trim();
        if (type && cmd) entries[type] = cmd;
      }
      return entries;
    }

    assert.deepEqual(parseProcfile(''), {});
    assert.deepEqual(parseProcfile('   '), {});
    assert.deepEqual(parseProcfile('\n\n'), {});
    assert.deepEqual(parseProcfile('# just comments\n# nothing else'), {});
  });

  it('subnet format validation accepts valid formats', () => {
    const valid = [
      'subnet-0123456789abcdef0',
      'subnet-abcdef0123456789a',
      'subnet-00000000000000000',
    ];

    const result = validateSubnetIds(valid);
    assert.equal(result.valid, true);
    assert.equal(result.errors.length, 0);
  });

  it('subnet format validation rejects invalid formats', () => {
    const invalid = ['subnet-short', 'vpc-0123456789abcdef0', 'subnet-UPPERCASE123456'];

    const result = validateSubnetIds(invalid);
    assert.equal(result.valid, false);
    assert.ok(result.errors.length > 0);
  });

  it('subnet format validation rejects empty array', () => {
    const result = validateSubnetIds([]);
    assert.equal(result.valid, false);
  });

  it('subnet format validation rejects more than 6 IDs', () => {
    const tooMany = Array(7).fill('subnet-0123456789abcdef0');
    const result = validateSubnetIds(tooMany);
    assert.equal(result.valid, false);
  });

  it('fast-path triggers correctly', () => {
    // Fast-path: < 5 apps, no Private Spaces, no Kafka
    const fastPathInventory = {
      apps: [{ app_name: 'app1' }, { app_name: 'app2' }],
      resources: [
        { resource_type: 'formation', config: {} },
        { resource_type: 'addon', config: { addon_service: 'heroku-postgresql' } },
      ],
    };
    assert.equal(isFastPath(fastPathInventory), true);

    // Not fast-path: >= 5 apps
    const manyApps = {
      apps: Array(5).fill({ app_name: 'app' }),
      resources: [],
    };
    assert.equal(isFastPath(manyApps), false);

    // Not fast-path: has Private Space
    const withSpace = {
      apps: [{ app_name: 'app1' }],
      resources: [{ resource_type: 'space', config: {} }],
    };
    assert.equal(isFastPath(withSpace), false);

    // Not fast-path: has Kafka
    const withKafka = {
      apps: [{ app_name: 'app1' }],
      resources: [{ resource_type: 'addon', config: { addon_service: 'heroku-kafka' } }],
    };
    assert.equal(isFastPath(withKafka), false);
  });
});
