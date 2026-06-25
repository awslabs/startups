// Feature: heroku-to-aws-migration
// Property-based tests for Generate Engine (Property 17)
//
// Run: node --test tests/property/heroku/generate.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

// --- Implementation: Migration Guide Generator (Property 17) ---

const DATA_STORE_PROCEDURES = {
  postgres: {
    title: 'PostgreSQL Migration Procedure',
    steps: [
      'Set up RDS/Aurora instance via Terraform',
      'Create pg_dump export from Heroku Postgres',
      'Transfer dump to S3 staging bucket',
      'Run pg_restore into target RDS/Aurora',
      'Validate row counts and schema integrity',
      'Update application connection strings',
      'Switch DNS and verify connectivity',
    ],
  },
  redis: {
    title: 'Redis Migration Procedure',
    steps: [
      'Provision ElastiCache Redis cluster via Terraform',
      'Export Redis data from Heroku (RDB snapshot or DUMP/RESTORE)',
      'Import data into ElastiCache',
      'Update application connection configuration',
      'Verify cache hit rates and connectivity',
    ],
  },
  kafka: {
    title: 'Kafka Migration Procedure',
    steps: [
      'Provision MSK cluster via Terraform',
      'Set up MirrorMaker 2 for topic replication',
      'Validate consumer group offsets',
      'Redirect producers to MSK endpoints',
      'Redirect consumers to MSK endpoints',
      'Decommission source Kafka cluster',
    ],
  },
};

function generateMigrationGuide(design) {
  const sections = [];

  // Determine which data store types are present
  const dataStoresPresent = new Set();
  for (const svc of design.services || []) {
    if (svc.aws_service === 'RDS PostgreSQL' || svc.aws_service === 'Aurora PostgreSQL') {
      dataStoresPresent.add('postgres');
    }
    if (svc.aws_service === 'ElastiCache Redis') {
      dataStoresPresent.add('redis');
    }
    if (svc.aws_service === 'Amazon MSK') {
      dataStoresPresent.add('kafka');
    }
  }

  // Include data migration procedures for present stores only
  for (const [storeType, procedure] of Object.entries(DATA_STORE_PROCEDURES)) {
    if (dataStoresPresent.has(storeType)) {
      sections.push({
        type: 'data_migration',
        store_type: storeType,
        title: procedure.title,
        steps: procedure.steps,
      });
    }
  }

  // Include deferred add-ons as manual migration items
  if (design.deferred && design.deferred.length > 0) {
    sections.push({
      type: 'manual_migration',
      title: 'Manual Migration Items (Deferred Add-ons)',
      items: design.deferred.map(d => ({
        addon_name: d.addon_name,
        reason: d.reason,
        recommendation: d.recommendation,
      })),
    });
  }

  return {
    title: 'MIGRATION_GUIDE.md',
    sections,
    data_stores_included: [...dataStoresPresent],
    deferred_count: design.deferred?.length || 0,
  };
}

// --- Generators ---

const arbPostgresService = fc.record({
  service_id: fc.constant('rds:app:postgres'),
  aws_service: fc.constantFrom('RDS PostgreSQL', 'Aurora PostgreSQL'),
  aws_config: fc.record({ region: fc.constant('us-east-1') }),
});

const arbRedisService = fc.record({
  service_id: fc.constant('elasticache:app:redis'),
  aws_service: fc.constant('ElastiCache Redis'),
  aws_config: fc.record({ region: fc.constant('us-east-1') }),
});

const arbKafkaService = fc.record({
  service_id: fc.constant('msk:app:kafka'),
  aws_service: fc.constant('Amazon MSK'),
  aws_config: fc.record({ region: fc.constant('us-east-1') }),
});

const arbFargateService = fc.record({
  service_id: fc.string({ minLength: 5, maxLength: 30 }),
  aws_service: fc.constant('Fargate'),
  aws_config: fc.record({ region: fc.constant('us-east-1') }),
});

const arbOtherService = fc.record({
  service_id: fc.string({ minLength: 5, maxLength: 30 }),
  aws_service: fc.constantFrom('CloudWatch Logs', 'Amazon SES', 'S3', 'ALB', 'EventBridge Scheduler'),
  aws_config: fc.record({ region: fc.constant('us-east-1') }),
});

const arbDeferredAddon = fc.record({
  addon_name: fc.stringOf(
    fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz-'),
    { minLength: 3, maxLength: 20 }
  ),
  reason: fc.constant('Not found in Fast_Path_Table'),
  recommendation: fc.constant('Engage AWS account team for replacement selection'),
});

const arbDesignWithDataStores = fc.record({
  services: fc.tuple(
    fc.array(arbFargateService, { minLength: 1, maxLength: 3 }),
    fc.array(arbOtherService, { minLength: 0, maxLength: 3 }),
    // Randomly include data stores
    fc.array(arbPostgresService, { minLength: 0, maxLength: 2 }),
    fc.array(arbRedisService, { minLength: 0, maxLength: 1 }),
    fc.array(arbKafkaService, { minLength: 0, maxLength: 1 }),
  ).map(([fargate, other, pg, redis, kafka]) => [...fargate, ...other, ...pg, ...redis, ...kafka]),
  deferred: fc.array(arbDeferredAddon, { minLength: 0, maxLength: 5 }),
});

// Design guaranteed to have all three data stores
const arbDesignAllStores = fc.record({
  services: fc.tuple(
    arbPostgresService,
    arbRedisService,
    arbKafkaService,
    fc.array(arbFargateService, { minLength: 1, maxLength: 2 }),
  ).map(([pg, redis, kafka, fargate]) => [pg, redis, kafka, ...fargate]),
  deferred: fc.array(arbDeferredAddon, { minLength: 0, maxLength: 3 }),
});

// Design with no data stores
const arbDesignNoDataStores = fc.record({
  services: fc.array(
    fc.oneof(arbFargateService, arbOtherService),
    { minLength: 1, maxLength: 5 }
  ),
  deferred: fc.array(arbDeferredAddon, { minLength: 0, maxLength: 3 }),
});

// --- Property Tests ---

describe('Feature: heroku-to-aws-migration, Property 17: Migration guide content matches design', () => {
  it('includes procedure for each present data store type', () => {
    fc.assert(fc.property(arbDesignAllStores, (design) => {
      const guide = generateMigrationGuide(design);

      assert.ok(guide.data_stores_included.includes('postgres'));
      assert.ok(guide.data_stores_included.includes('redis'));
      assert.ok(guide.data_stores_included.includes('kafka'));

      const dataSections = guide.sections.filter(s => s.type === 'data_migration');
      const storeTypes = dataSections.map(s => s.store_type);
      assert.ok(storeTypes.includes('postgres'));
      assert.ok(storeTypes.includes('redis'));
      assert.ok(storeTypes.includes('kafka'));
    }), { numRuns: 100 });
  });

  it('omits procedures for absent data store types', () => {
    fc.assert(fc.property(arbDesignNoDataStores, (design) => {
      const guide = generateMigrationGuide(design);

      assert.equal(guide.data_stores_included.length, 0);
      const dataSections = guide.sections.filter(s => s.type === 'data_migration');
      assert.equal(dataSections.length, 0);
    }), { numRuns: 100 });
  });

  it('includes deferred add-ons as manual migration items', () => {
    fc.assert(fc.property(arbDesignWithDataStores, (design) => {
      const guide = generateMigrationGuide(design);

      if (design.deferred.length > 0) {
        const manualSection = guide.sections.find(s => s.type === 'manual_migration');
        assert.ok(manualSection, 'Missing manual migration section for deferred add-ons');
        assert.equal(manualSection.items.length, design.deferred.length);

        for (const item of manualSection.items) {
          assert.ok(item.addon_name);
          assert.ok(item.reason);
          assert.ok(item.recommendation);
        }
      }

      assert.equal(guide.deferred_count, design.deferred.length);
    }), { numRuns: 100 });
  });

  it('only includes data stores that are actually in the design', () => {
    fc.assert(fc.property(arbDesignWithDataStores, (design) => {
      const guide = generateMigrationGuide(design);

      const hasPostgres = design.services.some(
        s => s.aws_service === 'RDS PostgreSQL' || s.aws_service === 'Aurora PostgreSQL'
      );
      const hasRedis = design.services.some(s => s.aws_service === 'ElastiCache Redis');
      const hasKafka = design.services.some(s => s.aws_service === 'Amazon MSK');

      assert.equal(guide.data_stores_included.includes('postgres'), hasPostgres);
      assert.equal(guide.data_stores_included.includes('redis'), hasRedis);
      assert.equal(guide.data_stores_included.includes('kafka'), hasKafka);
    }), { numRuns: 100 });
  });
});
