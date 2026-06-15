// Feature: heroku-to-aws-migration
// Property-based tests for Clarify Engine (Property 15)
//
// Run: node --test tests/property/heroku/clarify.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

// --- Implementation: Clarify Question Engine (Property 15) ---

const BATCH_1_QUESTIONS = [
  { id: 'Q1', topic: 'target_aws_region', batch: 1 },
  { id: 'Q2', topic: 'compliance', batch: 1 },
  { id: 'Q3', topic: 'availability_posture', batch: 1 },
  { id: 'Q4', topic: 'maintenance_window', batch: 1 },
  { id: 'Q5', topic: 'environment_naming', batch: 1 },
];

const BATCH_2_QUESTIONS = [
  { id: 'Q6', topic: 'database_ha', batch: 2 },
  { id: 'Q7', topic: 'redis_ha', batch: 2 },
  { id: 'Q8', topic: 'kafka_retention', batch: 2 },
  { id: 'Q9', topic: 'vpc_subnets', batch: 2 },
  { id: 'Q10', topic: 'dns_strategy', batch: 2 },
];

const BATCH_3_QUESTIONS = [
  { id: 'Q11', topic: 'fir_intent', batch: 3, conditional: 'fir_detected' },
  { id: 'Q12', topic: 'container_registry', batch: 3 },
  { id: 'Q13', topic: 'log_retention', batch: 3 },
  { id: 'Q14', topic: 'alerting_preference', batch: 3 },
  { id: 'Q15', topic: 'cost_optimization', batch: 3 },
];

const MAX_BATCH_SIZE = 5;

function isFastPath(inventory) {
  const appCount = inventory.apps ? inventory.apps.length : 0;
  const hasPrivateSpaces = inventory.resources?.some(r => r.resource_type === 'space') || false;
  const hasKafka = inventory.resources?.some(
    r => r.resource_type === 'addon' && r.config?.addon_service === 'heroku-kafka'
  ) || false;

  return appCount < 5 && !hasPrivateSpaces && !hasKafka;
}

function hasFirWorkloads(inventory) {
  return inventory.apps?.some(app => app.heroku_generation === 'fir') || false;
}

function generateQuestions(inventory) {
  const fastPath = isFastPath(inventory);
  const firDetected = hasFirWorkloads(inventory);

  if (fastPath) {
    // Fast-path: 3-5 questions from Batch 1
    const questions = BATCH_1_QUESTIONS.slice(0, fastPath ? 3 + Math.min(2, (inventory.apps?.length || 1)) : 5);
    // Include Fir question if detected even in fast-path
    if (firDetected) {
      const firQ = BATCH_3_QUESTIONS.find(q => q.topic === 'fir_intent');
      questions.push(firQ);
    }
    return questions.slice(0, 5);
  }

  // Full mode: 12-15 questions in batches ≤ 5
  let questions = [...BATCH_1_QUESTIONS, ...BATCH_2_QUESTIONS];

  // Batch 3: conditional questions
  for (const q of BATCH_3_QUESTIONS) {
    if (q.conditional === 'fir_detected' && !firDetected) continue;
    questions.push(q);
  }

  // Ensure range 12-15
  if (questions.length < 12) {
    // Pad with remaining batch 3
    const remaining = BATCH_3_QUESTIONS.filter(q => !questions.includes(q));
    while (questions.length < 12 && remaining.length > 0) {
      questions.push(remaining.shift());
    }
  }

  return questions.slice(0, 15);
}

function batchQuestions(questions) {
  const batches = [];
  for (let i = 0; i < questions.length; i += MAX_BATCH_SIZE) {
    batches.push(questions.slice(i, i + MAX_BATCH_SIZE));
  }
  return batches;
}

// --- Generators ---

const arbAppName = fc.stringOf(
  fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789-'),
  { minLength: 3, maxLength: 15 }
).filter(s => /^[a-z]/.test(s));

const arbApp = fc.record({
  app_name: arbAppName,
  app_id: fc.uuid(),
  heroku_generation: fc.constantFrom('cedar', 'fir', 'unknown'),
});

const arbResource = fc.record({
  resource_id: fc.string({ minLength: 5, maxLength: 30 }),
  resource_type: fc.constantFrom('formation', 'addon', 'space', 'pipeline'),
  heroku_app: arbAppName,
  config: fc.record({
    addon_service: fc.constantFrom('heroku-postgresql', 'heroku-redis', 'heroku-kafka', 'papertrail', null),
  }),
});

// Full inventory (≥5 apps OR private spaces OR Kafka)
const arbFullInventory = fc.record({
  apps: fc.array(arbApp, { minLength: 5, maxLength: 10 }),
  resources: fc.array(arbResource, { minLength: 1, maxLength: 15 }),
});

// Fast-path inventory (<5 apps, no private spaces, no Kafka)
const arbFastPathInventory = fc.record({
  apps: fc.array(
    fc.record({
      app_name: arbAppName,
      app_id: fc.uuid(),
      heroku_generation: fc.constantFrom('cedar', 'unknown'),
    }),
    { minLength: 1, maxLength: 4 }
  ),
  resources: fc.array(
    fc.record({
      resource_id: fc.string({ minLength: 5, maxLength: 30 }),
      resource_type: fc.constantFrom('formation', 'addon'),
      heroku_app: arbAppName,
      config: fc.record({
        addon_service: fc.constantFrom('heroku-postgresql', 'heroku-redis', 'papertrail', null),
      }),
    }),
    { minLength: 1, maxLength: 8 }
  ),
});

// Inventory with Fir workloads
const arbFirInventory = fc.record({
  apps: fc.tuple(
    fc.record({
      app_name: arbAppName,
      app_id: fc.uuid(),
      heroku_generation: fc.constant('fir'),
    }),
    fc.array(arbApp, { minLength: 4, maxLength: 8 })
  ).map(([firApp, others]) => [firApp, ...others]),
  resources: fc.array(arbResource, { minLength: 1, maxLength: 10 }),
});

// --- Property Tests ---

describe('Feature: heroku-to-aws-migration, Property 15: Clarify question count and batching', () => {
  it('full mode produces 12-15 questions', () => {
    fc.assert(fc.property(arbFullInventory, (inventory) => {
      const questions = generateQuestions(inventory);
      assert.ok(
        questions.length >= 12 && questions.length <= 15,
        `Expected 12-15 questions, got ${questions.length}`
      );
    }), { numRuns: 100 });
  });

  it('fast-path mode produces 3-5 questions', () => {
    fc.assert(fc.property(arbFastPathInventory, (inventory) => {
      const questions = generateQuestions(inventory);
      assert.ok(
        questions.length >= 3 && questions.length <= 5,
        `Expected 3-5 questions, got ${questions.length}`
      );
    }), { numRuns: 100 });
  });

  it('batches never exceed 5 questions', () => {
    fc.assert(fc.property(arbFullInventory, (inventory) => {
      const questions = generateQuestions(inventory);
      const batches = batchQuestions(questions);
      for (const batch of batches) {
        assert.ok(batch.length <= MAX_BATCH_SIZE, `Batch size ${batch.length} exceeds ${MAX_BATCH_SIZE}`);
      }
    }), { numRuns: 100 });
  });

  it('Fir intent question appears iff Fir detected', () => {
    fc.assert(fc.property(arbFirInventory, (inventory) => {
      const questions = generateQuestions(inventory);
      const hasFirQuestion = questions.some(q => q.topic === 'fir_intent');
      const firDetected = hasFirWorkloads(inventory);
      assert.equal(hasFirQuestion, firDetected);
    }), { numRuns: 100 });
  });

  it('Fir intent question absent when no Fir apps', () => {
    fc.assert(fc.property(arbFastPathInventory, (inventory) => {
      // Fast-path inventory has no Fir apps by construction
      const questions = generateQuestions(inventory);
      const hasFirQuestion = questions.some(q => q.topic === 'fir_intent');
      assert.equal(hasFirQuestion, false);
    }), { numRuns: 100 });
  });
});
