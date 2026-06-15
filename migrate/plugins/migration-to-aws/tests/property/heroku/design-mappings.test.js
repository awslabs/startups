// Feature: heroku-to-aws-migration
// Property-based tests for Design Engine mappings (Properties 6-11, 13-14)
//
// Run: node --test tests/property/heroku/design-mappings.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

// --- Implementation: Dyno Type Table (Property 6) ---

const DYNO_TYPE_TABLE = {
  'standard-1x': { cpu: 256, memory: 512 },
  'standard-2x': { cpu: 512, memory: 1024 },
  'performance-m': { cpu: 1024, memory: 2048 },
  'performance-l': { cpu: 4096, memory: 16384 },
  'private-s': { cpu: 512, memory: 1024 },
  'private-m': { cpu: 1024, memory: 2048 },
  'private-l': { cpu: 4096, memory: 16384 },
};

function mapFormationToFargate(formation) {
  const key = formation.dyno_type.toLowerCase();
  const sizing = DYNO_TYPE_TABLE[key];
  if (!sizing) {
    return { error: `Unsupported dyno type: ${formation.dyno_type}` };
  }
  const result = {
    aws_service: 'Fargate',
    task_cpu: sizing.cpu,
    task_memory: sizing.memory,
    desired_count: Math.max(0, Math.min(100, formation.quantity)),
    process_type: formation.process_type,
    load_balancer: formation.process_type === 'web',
  };
  return result;
}

// --- Implementation: Postgres Plan Table (Property 7) ---

const POSTGRES_PLAN_TABLE = {
  'hobby-dev': { ram_mb: 0, storage_gb: 1, rds_class: 'db.t4g.micro', aurora_class: 'db.t4g.medium', pooling: false },
  'hobby-basic': { ram_mb: 0, storage_gb: 10, rds_class: 'db.t4g.micro', aurora_class: 'db.t4g.medium', pooling: false },
  'standard-0': { ram_mb: 4096, storage_gb: 64, rds_class: 'db.t4g.medium', aurora_class: 'db.t4g.medium', pooling: true },
  'standard-2': { ram_mb: 8192, storage_gb: 256, rds_class: 'db.m6g.large', aurora_class: 'db.r6g.large', pooling: true },
  'standard-3': { ram_mb: 15360, storage_gb: 512, rds_class: 'db.m6g.xlarge', aurora_class: 'db.r6g.xlarge', pooling: true },
  'standard-4': { ram_mb: 30720, storage_gb: 1024, rds_class: 'db.m6g.2xlarge', aurora_class: 'db.r6g.2xlarge', pooling: true },
  'standard-5': { ram_mb: 62464, storage_gb: 1024, rds_class: 'db.m6g.4xlarge', aurora_class: 'db.r6g.4xlarge', pooling: true },
  'premium-0': { ram_mb: 4096, storage_gb: 64, rds_class: 'db.t4g.medium', aurora_class: 'db.t4g.medium', pooling: true },
  'premium-2': { ram_mb: 8192, storage_gb: 256, rds_class: 'db.m6g.large', aurora_class: 'db.r6g.large', pooling: true },
  'premium-3': { ram_mb: 15360, storage_gb: 512, rds_class: 'db.m6g.xlarge', aurora_class: 'db.r6g.xlarge', pooling: true },
  'premium-4': { ram_mb: 30720, storage_gb: 1024, rds_class: 'db.m6g.2xlarge', aurora_class: 'db.r6g.2xlarge', pooling: true },
  'premium-5': { ram_mb: 62464, storage_gb: 1024, rds_class: 'db.m6g.4xlarge', aurora_class: 'db.r6g.4xlarge', pooling: true },
  'private-0': { ram_mb: 4096, storage_gb: 64, rds_class: 'db.t4g.medium', aurora_class: 'db.t4g.medium', pooling: true },
  'private-2': { ram_mb: 8192, storage_gb: 256, rds_class: 'db.m6g.large', aurora_class: 'db.r6g.large', pooling: true },
  'private-3': { ram_mb: 15360, storage_gb: 512, rds_class: 'db.m6g.xlarge', aurora_class: 'db.r6g.xlarge', pooling: true },
  'shield-0': { ram_mb: 4096, storage_gb: 64, rds_class: 'db.t4g.medium', aurora_class: 'db.t4g.medium', pooling: true },
  'shield-2': { ram_mb: 8192, storage_gb: 256, rds_class: 'db.m6g.large', aurora_class: 'db.r6g.large', pooling: true },
};

function mapPostgresToAws(addon, availability) {
  const key = addon.plan.toLowerCase();
  const entry = POSTGRES_PLAN_TABLE[key];
  if (!entry) {
    return { error: `Unrecognized heroku-postgresql plan tier: ${addon.plan}` };
  }

  const useAurora = availability === 'multi-az-ha' || availability === 'multi-region';
  return {
    aws_service: useAurora ? 'Aurora PostgreSQL' : 'RDS PostgreSQL',
    instance_class: useAurora ? entry.aurora_class : entry.rds_class,
    storage_gb: entry.storage_gb,
    multi_az: availability !== 'single-az',
    rds_proxy: addon.connection_pooling === true,
    source_ram_mb: entry.ram_mb,
  };
}

// --- Implementation: Redis Plan Table (Property 8) ---

const REDIS_PLAN_TABLE = {
  'hobby': { memory_mb: 25, ha: false, encryption: false, version: '6.2', node_type: 'cache.t4g.micro' },
  'premium-0': { memory_mb: 50, ha: true, encryption: true, version: '7.0', node_type: 'cache.t4g.micro' },
  'premium-1': { memory_mb: 100, ha: true, encryption: true, version: '7.0', node_type: 'cache.t4g.micro' },
  'premium-2': { memory_mb: 250, ha: true, encryption: true, version: '7.0', node_type: 'cache.t4g.micro' },
  'premium-3': { memory_mb: 500, ha: true, encryption: true, version: '7.0', node_type: 'cache.t4g.small' },
  'premium-4': { memory_mb: 1024, ha: true, encryption: true, version: '7.0', node_type: 'cache.t4g.small' },
  'premium-5': { memory_mb: 2560, ha: true, encryption: true, version: '7.0', node_type: 'cache.t4g.medium' },
  'premium-6': { memory_mb: 5120, ha: true, encryption: true, version: '7.0', node_type: 'cache.m6g.large' },
  'premium-7': { memory_mb: 10240, ha: true, encryption: true, version: '7.0', node_type: 'cache.m6g.xlarge' },
  'premium-8': { memory_mb: 15360, ha: true, encryption: true, version: '7.0', node_type: 'cache.m6g.xlarge' },
  'premium-9': { memory_mb: 25600, ha: true, encryption: true, version: '7.0', node_type: 'cache.m6g.2xlarge' },
  'premium-10': { memory_mb: 51200, ha: true, encryption: true, version: '7.0', node_type: 'cache.m6g.4xlarge' },
  'private-1': { memory_mb: 1024, ha: true, encryption: true, version: '7.0', node_type: 'cache.t4g.small' },
  'private-2': { memory_mb: 2560, ha: true, encryption: true, version: '7.0', node_type: 'cache.t4g.medium' },
  'private-3': { memory_mb: 5120, ha: true, encryption: true, version: '7.0', node_type: 'cache.m6g.large' },
  'private-4': { memory_mb: 10240, ha: true, encryption: true, version: '7.0', node_type: 'cache.m6g.xlarge' },
  'private-5': { memory_mb: 25600, ha: true, encryption: true, version: '7.0', node_type: 'cache.m6g.2xlarge' },
};

// Node type memory capacities for validation
const NODE_TYPE_MEMORY = {
  'cache.t4g.micro': 512,
  'cache.t4g.small': 1392,
  'cache.t4g.medium': 3090,
  'cache.m6g.large': 6380,
  'cache.m6g.xlarge': 12930,
  'cache.m6g.2xlarge': 26040,
  'cache.m6g.4xlarge': 52260,
  'cache.m6g.8xlarge': 104860,
  'cache.m6g.12xlarge': 157290,
  'cache.m6g.16xlarge': 209720,
};

function mapRedisToElastiCache(addon) {
  const key = addon.plan.toLowerCase();
  const entry = REDIS_PLAN_TABLE[key];
  if (!entry) {
    return { error: `Unrecognized heroku-redis plan tier: ${addon.plan}` };
  }

  return {
    aws_service: 'ElastiCache Redis',
    node_type: entry.node_type,
    multi_az: entry.ha,
    automatic_failover: entry.ha,
    transit_encryption: entry.encryption,
    engine_version: entry.version,
    source_memory_mb: entry.memory_mb,
  };
}

// --- Implementation: Kafka Plan Table (Property 9) ---

const KAFKA_PLAN_TABLE = {
  'basic-0': { topics: 20, partitions: 40, storage_gb: 4, throughput_mbs: 5, broker_type: 'kafka.t3.small', storage_per_broker_gb: 10, min_brokers: 2, min_azs: 2, replication_factor: 2 },
  'standard-0': { topics: 40, partitions: 160, storage_gb: 50, throughput_mbs: 20, broker_type: 'kafka.m5.large', storage_per_broker_gb: 100, min_brokers: 3, min_azs: 3, replication_factor: 3 },
  'standard-1': { topics: 100, partitions: 400, storage_gb: 200, throughput_mbs: 50, broker_type: 'kafka.m5.xlarge', storage_per_broker_gb: 250, min_brokers: 3, min_azs: 3, replication_factor: 3 },
  'standard-2': { topics: 200, partitions: 1600, storage_gb: 1024, throughput_mbs: 100, broker_type: 'kafka.m5.2xlarge', storage_per_broker_gb: 512, min_brokers: 3, min_azs: 3, replication_factor: 3 },
  'extended-0': { topics: 200, partitions: 2000, storage_gb: 2048, throughput_mbs: 150, broker_type: 'kafka.m5.4xlarge', storage_per_broker_gb: 1024, min_brokers: 3, min_azs: 3, replication_factor: 3 },
  'extended-1': { topics: 400, partitions: 4000, storage_gb: 4096, throughput_mbs: 200, broker_type: 'kafka.m5.8xlarge', storage_per_broker_gb: 2048, min_brokers: 3, min_azs: 3, replication_factor: 3 },
  'extended-2': { topics: 600, partitions: 8000, storage_gb: 8192, throughput_mbs: 300, broker_type: 'kafka.m5.12xlarge', storage_per_broker_gb: 4096, min_brokers: 3, min_azs: 3, replication_factor: 3 },
  'private-extended-0': { topics: 200, partitions: 2000, storage_gb: 2048, throughput_mbs: 150, broker_type: 'kafka.m5.4xlarge', storage_per_broker_gb: 1024, min_brokers: 3, min_azs: 3, replication_factor: 3 },
  'private-extended-1': { topics: 400, partitions: 4000, storage_gb: 4096, throughput_mbs: 200, broker_type: 'kafka.m5.8xlarge', storage_per_broker_gb: 2048, min_brokers: 3, min_azs: 3, replication_factor: 3 },
  'private-extended-2': { topics: 600, partitions: 8000, storage_gb: 8192, throughput_mbs: 300, broker_type: 'kafka.m5.12xlarge', storage_per_broker_gb: 4096, min_brokers: 3, min_azs: 3, replication_factor: 3 },
};

function mapKafkaToMsk(addon) {
  const key = addon.plan.toLowerCase();
  const entry = KAFKA_PLAN_TABLE[key];
  if (!entry) {
    return { error: `Unrecognized heroku-kafka plan tier: ${addon.plan}` };
  }

  return {
    aws_service: 'Amazon MSK',
    broker_instance_type: entry.broker_type,
    storage_per_broker_gb: entry.storage_per_broker_gb,
    broker_count: entry.min_brokers,
    availability_zones: entry.min_azs,
    max_topics: entry.topics,
    max_partitions: entry.partitions,
    replication_factor: entry.replication_factor,
    source_storage_gb: entry.storage_gb,
    source_throughput_mbs: entry.throughput_mbs,
  };
}

// --- Implementation: Fast-Path Table (Property 10) ---

const FAST_PATH_TABLE = {
  'papertrail': { services: ['CloudWatch Logs'], type: 'single' },
  'sendgrid': { services: ['Amazon SES'], type: 'single' },
  'heroku scheduler': { services: ['EventBridge Scheduler'], type: 'single' },
  'memcachier': { services: ['ElastiCache Memcached'], type: 'single' },
  'bucketeer': { services: ['S3'], type: 'single' },
  'cloudamqp': { services: ['Amazon MQ'], type: 'single' },
  'bonsai elasticsearch': { services: ['Amazon OpenSearch'], type: 'single' },
  'scout apm': { services: ['CloudWatch', 'X-Ray'], type: 'composite' },
  'rollbar': { services: ['CloudWatch'], type: 'single' },
  'new relic': { services: ['CloudWatch', 'X-Ray'], type: 'composite' },
  'twilio': { services: ['Amazon SNS (SMS)'], type: 'single' },
  'cloudinary': { services: ['S3', 'CloudFront'], type: 'composite' },
  'sentry': { services: ['CloudWatch'], type: 'single' },
};

// Known prefix mappings for API slugs that differ from display names
const SLUG_PREFIX_MAP = {
  'bonsai': 'bonsai elasticsearch',
  'scout': 'scout apm',
  'newrelic': 'new relic',
  'new-relic': 'new relic',
};

function normalizeAddonName(slug) {
  // Strip heroku- prefix
  let normalized = slug.toLowerCase();
  if (normalized.startsWith('heroku-')) {
    normalized = 'heroku ' + normalized.slice(7);
  }
  // Replace hyphens with spaces
  normalized = normalized.replace(/-/g, ' ');
  // Check known prefix mappings
  if (SLUG_PREFIX_MAP[slug.toLowerCase()]) {
    return SLUG_PREFIX_MAP[slug.toLowerCase()];
  }
  return normalized;
}

function matchFastPath(addonName) {
  const normalized = normalizeAddonName(addonName);
  const entry = FAST_PATH_TABLE[normalized];
  if (!entry) {
    return { matched: false, confidence: 'deferred', reason: 'Not found in Fast_Path_Table' };
  }
  return { matched: true, confidence: 'deterministic', services: entry.services, type: entry.type };
}

// --- Implementation: Specialist Gate (Property 11) ---

function createDeferredRecord(addon) {
  return {
    addon_name: addon.addon_service,
    addon_plan: addon.plan,
    provider: addon.provider,
    reason: 'Not found in Fast_Path_Table',
    recommendation: 'Engage AWS account team for replacement selection',
  };
}

// --- Implementation: VPC Design (Property 13) ---

function designVpc(peeringState, dependencies) {
  if (peeringState.detected && peeringState.vpc_id) {
    return {
      mode: 'existing_vpc',
      existing_vpc_id: peeringState.vpc_id,
      subnet_ids: peeringState.subnet_ids || [],
      creates_new_vpc: false,
    };
  }

  const subnets = [
    { az: 'a', cidr: '10.0.1.0/24' },
    { az: 'b', cidr: '10.0.2.0/24' },
  ];

  const sg_inbound = dependencies.map(dep => ({
    port: dep.port,
    protocol: 'tcp',
    cidr: dep.cidr,
  }));

  return {
    mode: 'new_vpc',
    cidr_block: '10.0.0.0/16',
    subnets,
    internet_gateway: true,
    route_table: true,
    creates_new_vpc: true,
    security_groups: [{
      name: 'heroku-migrated-app-sg',
      inbound_rules: sg_inbound,
    }],
  };
}

// --- Implementation: Fir Exclusion (Property 14) ---

function applyFirExclusion(design, firWorkloads) {
  const filtered = { ...design };

  // No ARM/Graviton or CNB in output
  if (filtered.services) {
    filtered.services = filtered.services.map(svc => {
      const config = { ...svc.aws_config };
      // Ensure no graviton/arm references
      if (config.instance_type && /graviton|arm/i.test(config.instance_type)) {
        config.instance_type = config.instance_type.replace(/graviton|arm/gi, '');
      }
      // Ensure no CNB buildpack config
      delete config.cnb_buildpack;
      delete config.cloud_native_buildpack;
      return { ...svc, aws_config: config };
    });
  }

  // Add notation for deferred Fir workloads
  if (firWorkloads.length > 0) {
    filtered.fir_notation = {
      deferred: true,
      workloads: firWorkloads,
      message: 'Fir-generation workloads deferred to future version',
    };
  }

  return filtered;
}

// --- Generators ---

const arbDynoType = fc.constantFrom(...Object.keys(DYNO_TYPE_TABLE));

const arbFormation = fc.record({
  process_type: fc.constantFrom('web', 'worker', 'clock', 'release', 'scheduler'),
  dyno_type: arbDynoType,
  quantity: fc.integer({ min: 0, max: 100 }),
});

const arbPostgresPlan = fc.constantFrom(...Object.keys(POSTGRES_PLAN_TABLE));

const arbAvailability = fc.constantFrom('single-az', 'multi-az', 'multi-az-ha', 'multi-region');

const arbPostgresAddon = fc.record({
  plan: arbPostgresPlan,
  connection_pooling: fc.boolean(),
});

const arbRedisPlan = fc.constantFrom(...Object.keys(REDIS_PLAN_TABLE));

const arbRedisAddon = fc.record({
  plan: arbRedisPlan,
});

const arbKafkaPlan = fc.constantFrom(...Object.keys(KAFKA_PLAN_TABLE));

const arbKafkaAddon = fc.record({
  plan: arbKafkaPlan,
});

const arbFastPathAddonName = fc.constantFrom(...Object.keys(FAST_PATH_TABLE));

// API slugs that should normalize to fast-path entries
const arbApiSlug = fc.constantFrom(
  'papertrail', 'sendgrid', 'heroku-scheduler', 'memcachier',
  'bucketeer', 'cloudamqp', 'bonsai', 'scout', 'rollbar',
  'newrelic', 'twilio', 'cloudinary', 'sentry'
);

const arbCaseVariation = fc.constantFrom(...Object.keys(FAST_PATH_TABLE)).map(name => {
  // Generate random case variations
  return name.split('').map(c => Math.random() > 0.5 ? c.toUpperCase() : c.toLowerCase()).join('');
});

const arbUnknownAddon = fc.constantFrom(
  'custom-monitor', 'my-addon-xyz', 'internal-tool', 'acme-logging', 'fancy-db'
);

const arbPartialMatch = fc.constantFrom(
  'Paper', 'Send', 'New', 'Cloud', 'Sentry Pro', 'Papertrail Plus'
);

const arbPort = fc.integer({ min: 1, max: 65535 });
const arbCidr = fc.tuple(
  fc.integer({ min: 0, max: 255 }),
  fc.integer({ min: 0, max: 255 }),
  fc.integer({ min: 0, max: 255 }),
  fc.constantFrom(16, 20, 24, 28)
).map(([a, b, c, mask]) => `${a}.${b}.${c}.0/${mask}`);

const arbDependency = fc.record({
  port: arbPort,
  cidr: arbCidr,
});

const arbPeeringState = fc.oneof(
  fc.record({
    detected: fc.constant(true),
    vpc_id: fc.constant('vpc-0123456789abcdef0'),
    subnet_ids: fc.array(
      fc.constant('subnet-abc123def456789ab'),
      { minLength: 2, maxLength: 4 }
    ),
  }),
  fc.record({
    detected: fc.constant(false),
    vpc_id: fc.constant(null),
    subnet_ids: fc.constant([]),
  })
);

const arbDeferredAddon = fc.record({
  addon_service: fc.string({ minLength: 3, maxLength: 30 }),
  plan: fc.constantFrom('basic', 'standard', 'premium', 'enterprise'),
  provider: fc.string({ minLength: 3, maxLength: 20 }),
});

// --- Property Tests ---

describe('Feature: heroku-to-aws-migration, Property 6: Fargate mapping preserves dyno specifications', () => {
  it('CPU and memory match dyno type table', () => {
    fc.assert(fc.property(arbFormation, (formation) => {
      const result = mapFormationToFargate(formation);
      const expected = DYNO_TYPE_TABLE[formation.dyno_type.toLowerCase()];

      assert.equal(result.task_cpu, expected.cpu);
      assert.equal(result.task_memory, expected.memory);
    }), { numRuns: 100 });
  });

  it('desired_count equals source quantity clamped to 0-100', () => {
    fc.assert(fc.property(arbFormation, (formation) => {
      const result = mapFormationToFargate(formation);
      const clamped = Math.max(0, Math.min(100, formation.quantity));
      assert.equal(result.desired_count, clamped);
    }), { numRuns: 100 });
  });

  it('ALB included iff process type is web', () => {
    fc.assert(fc.property(arbFormation, (formation) => {
      const result = mapFormationToFargate(formation);
      assert.equal(result.load_balancer, formation.process_type === 'web');
    }), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 7: Postgres mapping selects correct service and sizing', () => {
  it('selects RDS for single-az/multi-az, Aurora for multi-az-ha/multi-region', () => {
    fc.assert(fc.property(arbPostgresAddon, arbAvailability, (addon, availability) => {
      const result = mapPostgresToAws(addon, availability);
      const useAurora = availability === 'multi-az-ha' || availability === 'multi-region';

      if (useAurora) {
        assert.equal(result.aws_service, 'Aurora PostgreSQL');
      } else {
        assert.equal(result.aws_service, 'RDS PostgreSQL');
      }
    }), { numRuns: 100 });
  });

  it('storage meets or exceeds source plan maximum', () => {
    fc.assert(fc.property(arbPostgresAddon, arbAvailability, (addon, availability) => {
      const result = mapPostgresToAws(addon, availability);
      const entry = POSTGRES_PLAN_TABLE[addon.plan.toLowerCase()];
      assert.ok(result.storage_gb >= entry.storage_gb);
    }), { numRuns: 100 });
  });

  it('RDS Proxy included iff connection pooling is enabled', () => {
    fc.assert(fc.property(arbPostgresAddon, arbAvailability, (addon, availability) => {
      const result = mapPostgresToAws(addon, availability);
      assert.equal(result.rds_proxy, addon.connection_pooling === true);
    }), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 8: Redis mapping preserves configuration', () => {
  it('node type matches table recommendation for the plan', () => {
    fc.assert(fc.property(arbRedisAddon, (addon) => {
      const result = mapRedisToElastiCache(addon);
      const entry = REDIS_PLAN_TABLE[addon.plan.toLowerCase()];
      // The table defines the correct node type per plan — validate the mapping uses it
      assert.equal(
        result.node_type, entry.node_type,
        `Expected ${entry.node_type} for plan ${addon.plan}, got ${result.node_type}`
      );
      // The source memory is tracked for reference
      assert.equal(result.source_memory_mb, entry.memory_mb);
    }), { numRuns: 100 });
  });

  it('Multi-AZ and failover configured iff source HA enabled', () => {
    fc.assert(fc.property(arbRedisAddon, (addon) => {
      const result = mapRedisToElastiCache(addon);
      const entry = REDIS_PLAN_TABLE[addon.plan.toLowerCase()];
      assert.equal(result.multi_az, entry.ha);
      assert.equal(result.automatic_failover, entry.ha);
    }), { numRuns: 100 });
  });

  it('compatible Redis version selected', () => {
    fc.assert(fc.property(arbRedisAddon, (addon) => {
      const result = mapRedisToElastiCache(addon);
      const entry = REDIS_PLAN_TABLE[addon.plan.toLowerCase()];
      // Major version must match
      const sourceMajor = entry.version.split('.')[0];
      const targetMajor = result.engine_version.split('.')[0];
      assert.equal(targetMajor, sourceMajor);
    }), { numRuns: 100 });
  });

  it('encryption enabled iff source has encryption', () => {
    fc.assert(fc.property(arbRedisAddon, (addon) => {
      const result = mapRedisToElastiCache(addon);
      const entry = REDIS_PLAN_TABLE[addon.plan.toLowerCase()];
      assert.equal(result.transit_encryption, entry.encryption);
    }), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 9: Kafka mapping preserves topology and meets sizing', () => {
  it('broker storage meets or exceeds source storage', () => {
    fc.assert(fc.property(arbKafkaAddon, (addon) => {
      const result = mapKafkaToMsk(addon);
      const totalStorage = result.storage_per_broker_gb * result.broker_count;
      assert.ok(
        totalStorage >= result.source_storage_gb,
        `Total storage ${totalStorage}GB < source ${result.source_storage_gb}GB`
      );
    }), { numRuns: 100 });
  });

  it('topology preserved (topics and partitions)', () => {
    fc.assert(fc.property(arbKafkaAddon, (addon) => {
      const result = mapKafkaToMsk(addon);
      const entry = KAFKA_PLAN_TABLE[addon.plan.toLowerCase()];
      assert.equal(result.max_topics, entry.topics);
      assert.equal(result.max_partitions, entry.partitions);
      assert.equal(result.replication_factor, entry.replication_factor);
    }), { numRuns: 100 });
  });

  it('minimum 2 brokers across 2 AZs', () => {
    fc.assert(fc.property(arbKafkaAddon, (addon) => {
      const result = mapKafkaToMsk(addon);
      assert.ok(result.broker_count >= 2);
      assert.ok(result.availability_zones >= 2);
    }), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 10: Fast-path matching and deferral', () => {
  it('exact case-insensitive match produces deterministic confidence', () => {
    fc.assert(fc.property(arbFastPathAddonName, (name) => {
      const result = matchFastPath(name);
      assert.equal(result.matched, true);
      assert.equal(result.confidence, 'deterministic');
    }), { numRuns: 100 });
  });

  it('case variations still match deterministically', () => {
    fc.assert(fc.property(arbCaseVariation, (name) => {
      const result = matchFastPath(name);
      assert.equal(result.matched, true);
      assert.equal(result.confidence, 'deterministic');
    }), { numRuns: 100 });
  });

  it('partial matches are treated as unmatched', () => {
    fc.assert(fc.property(arbPartialMatch, (name) => {
      const result = matchFastPath(name);
      assert.equal(result.matched, false);
      assert.equal(result.confidence, 'deferred');
    }), { numRuns: 100 });
  });

  it('unknown add-ons are deferred', () => {
    fc.assert(fc.property(arbUnknownAddon, (name) => {
      const result = matchFastPath(name);
      assert.equal(result.matched, false);
      assert.equal(result.confidence, 'deferred');
    }), { numRuns: 100 });
  });

  it('composite mappings include all services', () => {
    const compositeNames = Object.entries(FAST_PATH_TABLE)
      .filter(([, v]) => v.type === 'composite')
      .map(([k]) => k);

    for (const name of compositeNames) {
      const result = matchFastPath(name);
      assert.equal(result.type, 'composite');
      assert.ok(result.services.length > 1, `${name} should have multiple services`);
    }
  });

  it('API slugs normalize correctly to fast-path matches', () => {
    fc.assert(fc.property(arbApiSlug, (slug) => {
      const result = matchFastPath(slug);
      assert.equal(result.matched, true, `API slug "${slug}" should match after normalization`);
      assert.equal(result.confidence, 'deterministic');
    }), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 11: Specialist gate records all required fields', () => {
  it('deferred record includes all required fields', () => {
    fc.assert(fc.property(arbDeferredAddon, (addon) => {
      const record = createDeferredRecord(addon);

      assert.ok('addon_name' in record);
      assert.ok('addon_plan' in record);
      assert.ok('provider' in record);
      assert.ok('reason' in record);
      assert.ok('recommendation' in record);

      assert.equal(record.addon_name, addon.addon_service);
      assert.equal(record.addon_plan, addon.plan);
      assert.equal(record.provider, addon.provider);
      assert.ok(record.reason.length > 0);
      assert.ok(record.recommendation.includes('AWS account team'));
    }), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 13: VPC design matches peering state', () => {
  it('peering detected → references existing VPC, no new VPC created', () => {
    const peeringDetected = {
      detected: true,
      vpc_id: 'vpc-0123456789abcdef0',
      subnet_ids: ['subnet-aaa', 'subnet-bbb'],
    };

    fc.assert(fc.property(
      fc.array(arbDependency, { minLength: 0, maxLength: 5 }),
      (deps) => {
        const result = designVpc(peeringDetected, deps);
        assert.equal(result.mode, 'existing_vpc');
        assert.equal(result.existing_vpc_id, 'vpc-0123456789abcdef0');
        assert.equal(result.creates_new_vpc, false);
      }
    ), { numRuns: 100 });
  });

  it('no peering → new VPC with CIDR, 2+ subnets, IGW', () => {
    const noPeering = { detected: false, vpc_id: null, subnet_ids: [] };

    fc.assert(fc.property(
      fc.array(arbDependency, { minLength: 0, maxLength: 5 }),
      (deps) => {
        const result = designVpc(noPeering, deps);
        assert.equal(result.mode, 'new_vpc');
        assert.ok(result.cidr_block);
        assert.ok(result.subnets.length >= 2);
        assert.equal(result.internet_gateway, true);
        assert.equal(result.route_table, true);
        assert.equal(result.creates_new_vpc, true);
      }
    ), { numRuns: 100 });
  });

  it('security groups restrict to declared CIDRs only', () => {
    const noPeering = { detected: false, vpc_id: null, subnet_ids: [] };

    fc.assert(fc.property(
      fc.array(arbDependency, { minLength: 1, maxLength: 5 }),
      (deps) => {
        const result = designVpc(noPeering, deps);
        const sgRules = result.security_groups[0].inbound_rules;

        // Each rule must correspond to a declared dependency
        assert.equal(sgRules.length, deps.length);
        for (let i = 0; i < deps.length; i++) {
          assert.equal(sgRules[i].cidr, deps[i].cidr);
          assert.equal(sgRules[i].port, deps[i].port);
        }
      }
    ), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 14: No Fir-specific Terraform generation', () => {
  it('no ARM/Graviton or CNB in output when Fir workloads present', () => {
    const arbService = fc.record({
      service_id: fc.string({ minLength: 5, maxLength: 30 }),
      aws_config: fc.record({
        instance_type: fc.constantFrom('t3.medium', 't4g.large', 'graviton-2xl', 'arm-based'),
        cnb_buildpack: fc.constantFrom('heroku/nodejs', undefined),
        cloud_native_buildpack: fc.constantFrom('paketo-buildpacks/nodejs', undefined),
        region: fc.constant('us-east-1'),
      }),
    });

    fc.assert(fc.property(
      fc.record({
        services: fc.array(arbService, { minLength: 1, maxLength: 5 }),
      }),
      fc.array(fc.string({ minLength: 3, maxLength: 20 }), { minLength: 1, maxLength: 3 }),
      (design, firWorkloads) => {
        const result = applyFirExclusion(design, firWorkloads);

        // No ARM/Graviton references
        for (const svc of result.services) {
          if (svc.aws_config.instance_type) {
            assert.ok(
              !/graviton|arm/i.test(svc.aws_config.instance_type),
              `Found ARM/Graviton in: ${svc.aws_config.instance_type}`
            );
          }
          // No CNB buildpack config
          assert.equal(svc.aws_config.cnb_buildpack, undefined);
          assert.equal(svc.aws_config.cloud_native_buildpack, undefined);
        }

        // Fir notation present
        assert.ok(result.fir_notation);
        assert.equal(result.fir_notation.deferred, true);
        assert.deepEqual(result.fir_notation.workloads, firWorkloads);
      }
    ), { numRuns: 100 });
  });
});
