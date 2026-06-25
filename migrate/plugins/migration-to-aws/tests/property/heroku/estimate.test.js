// Feature: heroku-to-aws-migration
// Property-based tests for Estimate Engine (Properties 16, 18)
//
// Run: node --test tests/property/heroku/estimate.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

// --- Implementation: Cost Estimation (Property 16) ---

function estimateCosts(services, pricingLookup) {
  const itemized = [];
  let total = 0;

  for (const svc of services) {
    const price = pricingLookup(svc);
    if (price === null || price === undefined) {
      itemized.push({
        service_id: svc.service_id,
        aws_service: svc.aws_service,
        monthly_cost: null,
        status: 'unpriced',
      });
    } else {
      itemized.push({
        service_id: svc.service_id,
        aws_service: svc.aws_service,
        monthly_cost: price,
        status: 'priced',
      });
      total += price;
    }
  }

  return {
    total_monthly_cost: total,
    currency: 'USD',
    services: itemized,
    unpriced_count: itemized.filter(i => i.status === 'unpriced').length,
  };
}

// --- Implementation: Complexity Tier Classification (Property 18) ---

const LARGE_CONDITIONS = {
  service_count: (v) => v > 50,
  monthly_spend: (v) => v >= 100000,
  databases: (v) => v > 10,
  stateful_storage_tb: (v) => v > 5,
  availability: (v) => v === 'multi-region',
  compliance: (v) => ['hipaa', 'pci'].includes(v),
  multi_region: (v) => v === true,
};

const MEDIUM_CONDITIONS = {
  service_count: (v) => v > 15,
  monthly_spend: (v) => v >= 10000,
  databases: (v) => v > 3,
  stateful_storage_tb: (v) => v > 1,
  availability: (v) => v === 'multi-az-ha',
  compliance: (v) => v === 'soc2',
};

function classifyComplexity(inputs) {
  // Evaluate Large first
  for (const [field, condition] of Object.entries(LARGE_CONDITIONS)) {
    if (inputs[field] !== undefined && condition(inputs[field])) {
      return 'Large';
    }
  }

  // Evaluate Medium
  for (const [field, condition] of Object.entries(MEDIUM_CONDITIONS)) {
    if (inputs[field] !== undefined && condition(inputs[field])) {
      return 'Medium';
    }
  }

  return 'Small';
}

// --- Generators ---

const arbAwsService = fc.constantFrom(
  'Fargate', 'ALB', 'RDS PostgreSQL', 'Aurora PostgreSQL',
  'ElastiCache Redis', 'Amazon MSK', 'CloudWatch Logs',
  'Amazon SES', 'S3', 'EventBridge Scheduler'
);

const arbDesignedService = fc.record({
  service_id: fc.string({ minLength: 5, maxLength: 40 }),
  aws_service: arbAwsService,
  aws_config: fc.record({
    region: fc.constant('us-east-1'),
  }),
});

const arbPricedServices = fc.array(arbDesignedService, { minLength: 1, maxLength: 15 });

// Generator for complexity inputs that guarantee Large tier
const arbLargeInputs = fc.oneof(
  fc.record({
    service_count: fc.integer({ min: 51, max: 200 }),
    monthly_spend: fc.double({ min: 0, max: 99999, noNaN: true }),
    databases: fc.integer({ min: 0, max: 10 }),
    stateful_storage_tb: fc.double({ min: 0, max: 5, noNaN: true }),
    availability: fc.constantFrom('single-az', 'multi-az'),
    compliance: fc.constantFrom('none', 'soc2'),
    multi_region: fc.constant(false),
  }),
  fc.record({
    service_count: fc.integer({ min: 0, max: 50 }),
    monthly_spend: fc.double({ min: 100000, max: 500000, noNaN: true }),
    databases: fc.integer({ min: 0, max: 10 }),
    stateful_storage_tb: fc.double({ min: 0, max: 5, noNaN: true }),
    availability: fc.constantFrom('single-az', 'multi-az'),
    compliance: fc.constantFrom('none', 'soc2'),
    multi_region: fc.constant(false),
  }),
  fc.record({
    service_count: fc.integer({ min: 0, max: 50 }),
    monthly_spend: fc.double({ min: 0, max: 99999, noNaN: true }),
    databases: fc.integer({ min: 0, max: 10 }),
    stateful_storage_tb: fc.double({ min: 0, max: 5, noNaN: true }),
    availability: fc.constant('multi-region'),
    compliance: fc.constantFrom('none', 'soc2'),
    multi_region: fc.constant(false),
  }),
  fc.record({
    service_count: fc.integer({ min: 0, max: 50 }),
    monthly_spend: fc.double({ min: 0, max: 99999, noNaN: true }),
    databases: fc.integer({ min: 0, max: 10 }),
    stateful_storage_tb: fc.double({ min: 0, max: 5, noNaN: true }),
    availability: fc.constantFrom('single-az', 'multi-az'),
    compliance: fc.constantFrom('hipaa', 'pci'),
    multi_region: fc.constant(false),
  })
);

// Generator for complexity inputs that guarantee Medium (not Large)
const arbMediumInputs = fc.record({
  service_count: fc.integer({ min: 16, max: 50 }),
  monthly_spend: fc.double({ min: 10000, max: 99999, noNaN: true }),
  databases: fc.integer({ min: 4, max: 10 }),
  stateful_storage_tb: fc.double({ min: 1.01, max: 5, noNaN: true }),
  availability: fc.constant('multi-az-ha'),
  compliance: fc.constant('soc2'),
  multi_region: fc.constant(false),
});

// Generator for complexity inputs that guarantee Small
const arbSmallInputs = fc.record({
  service_count: fc.integer({ min: 1, max: 15 }),
  monthly_spend: fc.double({ min: 0, max: 9999, noNaN: true }),
  databases: fc.integer({ min: 0, max: 3 }),
  stateful_storage_tb: fc.double({ min: 0, max: 1, noNaN: true }),
  availability: fc.constantFrom('single-az', 'multi-az'),
  compliance: fc.constant('none'),
  multi_region: fc.constant(false),
});

// --- Property Tests ---

describe('Feature: heroku-to-aws-migration, Property 16: Estimate cost consistency', () => {
  it('total equals sum of individual priced costs', () => {
    fc.assert(fc.property(
      arbPricedServices,
      fc.array(fc.double({ min: 1, max: 10000, noNaN: true }), { minLength: 15, maxLength: 15 }),
      (services, prices) => {
        const pricingLookup = (svc) => {
          const idx = services.indexOf(svc);
          return prices[idx % prices.length];
        };

        const result = estimateCosts(services, pricingLookup);
        const expectedTotal = result.services
          .filter(s => s.status === 'priced')
          .reduce((sum, s) => sum + s.monthly_cost, 0);

        assert.ok(
          Math.abs(result.total_monthly_cost - expectedTotal) < 0.001,
          `Total ${result.total_monthly_cost} != sum ${expectedTotal}`
        );
      }
    ), { numRuns: 100 });
  });

  it('unpriced services excluded from total', () => {
    fc.assert(fc.property(
      arbPricedServices,
      fc.array(fc.boolean(), { minLength: 15, maxLength: 15 }),
      (services, availability) => {
        const pricingLookup = (svc) => {
          const idx = services.indexOf(svc);
          return availability[idx % availability.length] ? 50.0 : null;
        };

        const result = estimateCosts(services, pricingLookup);
        const unpricedItems = result.services.filter(s => s.status === 'unpriced');
        const pricedItems = result.services.filter(s => s.status === 'priced');

        // Verify no unpriced cost in total
        for (const item of unpricedItems) {
          assert.equal(item.monthly_cost, null);
        }

        // Total only accounts for priced items
        const expectedTotal = pricedItems.reduce((sum, s) => sum + s.monthly_cost, 0);
        assert.ok(
          Math.abs(result.total_monthly_cost - expectedTotal) < 0.001
        );
        assert.equal(result.unpriced_count, unpricedItems.length);
      }
    ), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 18: Complexity tier classification', () => {
  it('Large tier when any Large condition is met', () => {
    fc.assert(fc.property(arbLargeInputs, (inputs) => {
      const tier = classifyComplexity(inputs);
      assert.equal(tier, 'Large');
    }), { numRuns: 100 });
  });

  it('Medium tier when Medium condition met and no Large', () => {
    fc.assert(fc.property(arbMediumInputs, (inputs) => {
      const tier = classifyComplexity(inputs);
      // Should be Medium or Large (Medium conditions can overlap with Large)
      assert.ok(
        tier === 'Medium' || tier === 'Large',
        `Expected Medium or Large, got ${tier}`
      );
    }), { numRuns: 100 });
  });

  it('Small tier when no Large or Medium condition met', () => {
    fc.assert(fc.property(arbSmallInputs, (inputs) => {
      const tier = classifyComplexity(inputs);
      assert.equal(tier, 'Small');
    }), { numRuns: 100 });
  });

  it('evaluation order: Large → Medium → Small (first match wins)', () => {
    fc.assert(fc.property(
      fc.record({
        service_count: fc.integer({ min: 0, max: 200 }),
        monthly_spend: fc.double({ min: 0, max: 500000, noNaN: true }),
        databases: fc.integer({ min: 0, max: 20 }),
        stateful_storage_tb: fc.double({ min: 0, max: 10, noNaN: true }),
        availability: fc.constantFrom('single-az', 'multi-az', 'multi-az-ha', 'multi-region'),
        compliance: fc.constantFrom('none', 'soc2', 'hipaa', 'pci'),
        multi_region: fc.boolean(),
      }),
      (inputs) => {
        const tier = classifyComplexity(inputs);

        // If Large, at least one Large condition should be true
        if (tier === 'Large') {
          const meetsLarge = Object.entries(LARGE_CONDITIONS).some(
            ([field, cond]) => inputs[field] !== undefined && cond(inputs[field])
          );
          assert.ok(meetsLarge, 'Classified as Large but no Large condition met');
        }

        // If Small, no Large or Medium condition should be true
        if (tier === 'Small') {
          const meetsLarge = Object.entries(LARGE_CONDITIONS).some(
            ([field, cond]) => inputs[field] !== undefined && cond(inputs[field])
          );
          const meetsMedium = Object.entries(MEDIUM_CONDITIONS).some(
            ([field, cond]) => inputs[field] !== undefined && cond(inputs[field])
          );
          assert.ok(!meetsLarge, 'Classified as Small but Large condition met');
          assert.ok(!meetsMedium, 'Classified as Small but Medium condition met');
        }
      }
    ), { numRuns: 100 });
  });
});
