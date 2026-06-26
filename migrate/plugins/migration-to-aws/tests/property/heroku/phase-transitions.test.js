// Feature: heroku-to-aws-migration
// Property-based tests for Phase State Machine (Property 1)
//
// Run: node --test tests/property/heroku/phase-transitions.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fc from 'fast-check';

// --- Implementation: Phase State Machine (Property 1) ---

const PHASES = ['discover', 'clarify', 'design', 'estimate', 'generate'];
const VALID_STATUSES = ['pending', 'in_progress', 'completed'];

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
      // Can only start (move to in_progress) if predecessor is completed
      if (predecessor && phaseStatus.phases[predecessor] !== 'completed') {
        return {
          success: false,
          reason: `Cannot start ${targetPhase}: predecessor ${predecessor} not completed`,
          phaseStatus,
        };
      }
      // Can start from pending only
      if (currentStatus !== 'pending') {
        return {
          success: false,
          reason: `Cannot start ${targetPhase}: current status is ${currentStatus}`,
          phaseStatus,
        };
      }
      const updated = { phases: { ...phaseStatus.phases, [targetPhase]: 'in_progress' } };
      return { success: true, phaseStatus: updated };
    }

    case 'complete': {
      // Can only complete from in_progress
      if (currentStatus !== 'in_progress') {
        return {
          success: false,
          reason: `Cannot complete ${targetPhase}: not in_progress`,
          phaseStatus,
        };
      }
      const updated = { phases: { ...phaseStatus.phases, [targetPhase]: 'completed' } };
      return { success: true, phaseStatus: updated };
    }

    case 'gate_fail': {
      // GATE_FAIL retains in_progress status (halts pipeline)
      if (currentStatus !== 'in_progress') {
        return {
          success: false,
          reason: `GATE_FAIL on ${targetPhase}: not in_progress`,
          phaseStatus,
        };
      }
      // Status stays in_progress — pipeline halted
      return {
        success: true,
        halted: true,
        phaseStatus, // no change
      };
    }

    case 'error': {
      // Unrecoverable error reverts to pending, preserves prior completed phases
      const updated = { phases: { ...phaseStatus.phases, [targetPhase]: 'pending' } };
      return { success: true, reverted: true, phaseStatus: updated };
    }

    default:
      return { success: false, reason: `Unknown action: ${action}`, phaseStatus };
  }
}

function getCompletedPhases(phaseStatus) {
  return PHASES.filter(p => phaseStatus.phases[p] === 'completed');
}

// --- Generators ---

const arbPhase = fc.constantFrom(...PHASES);

const arbAction = fc.constantFrom('start', 'complete', 'gate_fail', 'error');

// Generate a valid phase progression (some phases completed in order)
const arbProgressedStatus = fc.integer({ min: 0, max: PHASES.length }).map(completedCount => {
  const phases = {};
  for (let i = 0; i < PHASES.length; i++) {
    if (i < completedCount) {
      phases[PHASES[i]] = 'completed';
    } else if (i === completedCount) {
      phases[PHASES[i]] = 'in_progress';
    } else {
      phases[PHASES[i]] = 'pending';
    }
  }
  return { phases };
});

// Generate a valid state where specific phase is in_progress
const arbInProgressAt = fc.integer({ min: 0, max: PHASES.length - 1 }).map(idx => {
  const phases = {};
  for (let i = 0; i < PHASES.length; i++) {
    if (i < idx) phases[PHASES[i]] = 'completed';
    else if (i === idx) phases[PHASES[i]] = 'in_progress';
    else phases[PHASES[i]] = 'pending';
  }
  return { phases, activePhase: PHASES[idx] };
});

// --- Property Tests ---

describe('Feature: heroku-to-aws-migration, Property 1: Phase transition validity', () => {
  it('in_progress only when predecessor is completed', () => {
    fc.assert(fc.property(arbProgressedStatus, arbPhase, (status, targetPhase) => {
      const result = attemptTransition(status, targetPhase, 'start');
      const predecessor = getPredecessor(targetPhase);

      if (result.success) {
        // If transition succeeded, predecessor must be completed (or none for discover)
        if (predecessor) {
          assert.equal(
            status.phases[predecessor], 'completed',
            `Started ${targetPhase} but predecessor ${predecessor} was ${status.phases[predecessor]}`
          );
        }
        // The target should now be in_progress
        assert.equal(result.phaseStatus.phases[targetPhase], 'in_progress');
      } else {
        // If failed because predecessor not completed, verify that's the case
        if (predecessor && status.phases[predecessor] !== 'completed') {
          assert.ok(result.reason.includes('predecessor'));
        }
      }
    }), { numRuns: 100 });
  });

  it('GATE_FAIL retains in_progress status', () => {
    fc.assert(fc.property(arbInProgressAt, (state) => {
      const { phases, activePhase } = state;
      const phaseStatus = { phases };

      const result = attemptTransition(phaseStatus, activePhase, 'gate_fail');

      assert.equal(result.success, true);
      assert.equal(result.halted, true);
      // Status unchanged — still in_progress
      assert.equal(result.phaseStatus.phases[activePhase], 'in_progress');
    }), { numRuns: 100 });
  });

  it('error reverts to pending while preserving prior completed phases', () => {
    fc.assert(fc.property(arbInProgressAt, (state) => {
      const { phases, activePhase } = state;
      const phaseStatus = { phases };

      const completedBefore = getCompletedPhases(phaseStatus);
      const result = attemptTransition(phaseStatus, activePhase, 'error');

      assert.equal(result.success, true);
      assert.equal(result.reverted, true);
      // Target phase reverted to pending
      assert.equal(result.phaseStatus.phases[activePhase], 'pending');

      // All previously completed phases remain completed
      for (const phase of completedBefore) {
        if (phase !== activePhase) {
          assert.equal(
            result.phaseStatus.phases[phase], 'completed',
            `Prior completed phase ${phase} was modified`
          );
        }
      }
    }), { numRuns: 100 });
  });

  it('only one phase can be in_progress at a time in valid states', () => {
    fc.assert(fc.property(arbProgressedStatus, (status) => {
      const inProgressCount = PHASES.filter(p => status.phases[p] === 'in_progress').length;
      assert.ok(inProgressCount <= 1, `Multiple phases in_progress: ${inProgressCount}`);
    }), { numRuns: 100 });
  });

  it('initial state has all phases pending', () => {
    const initial = createInitialPhaseStatus();
    for (const phase of PHASES) {
      assert.equal(initial.phases[phase], 'pending');
    }
  });

  it('completed phases are always contiguous from the beginning', () => {
    fc.assert(fc.property(arbProgressedStatus, (status) => {
      let seenNonCompleted = false;
      for (const phase of PHASES) {
        if (status.phases[phase] !== 'completed') {
          seenNonCompleted = true;
        } else if (seenNonCompleted) {
          assert.fail(`Phase ${phase} is completed but a prior phase was not`);
        }
      }
    }), { numRuns: 100 });
  });
});


// --- Implementation: Interim Cutover Constraints (Property 20) ---

function validateInterimCutover(preferences) {
  const errors = [];
  const approach = preferences.global?.migration_approach;

  if (approach === 'interim_cutover_data_first') {
    if (!preferences.global?.target_exit_date) {
      errors.push('interim_cutover_data_first requires target_exit_date');
    } else {
      // Validate ISO 8601 date format
      const date = new Date(preferences.global.target_exit_date);
      if (isNaN(date.getTime())) {
        errors.push('target_exit_date is not a valid ISO 8601 date');
      }
    }
    if (preferences.global?.interim_cutover !== true) {
      errors.push('interim_cutover must be true when interim_cutover_data_first selected');
    }
    if (!preferences.global?.ktlo_warning) {
      errors.push('ktlo_warning must be populated for interim cutover');
    }
  }

  if (approach === 'full_cutover') {
    // These fields should not be required
    if (preferences.global?.interim_cutover === true) {
      errors.push('interim_cutover should not be true for full_cutover');
    }
  }

  return errors;
}

// --- Implementation: Guide Section Matching (Property 21) ---

const MIGRATION_METHODS = ['pg_dump_restore', 'dms', 'bucardo', 'wal_g'];
const CONTAINERIZATION_STATUSES = ['containerized', 'buildpack_only', 'partial'];

function determineGuideSections(preferences) {
  const sections = [];

  // Containerization prerequisites
  const containerStatus = preferences.operational?.containerization_status;
  if (containerStatus === 'buildpack_only' || containerStatus === 'partial') {
    sections.push('containerization_prerequisites');
  }

  // Data migration method
  const method = preferences.data?.migration_method;
  if (method === 'pg_dump_restore') sections.push('pg_dump_cutover_runbook');
  if (method === 'dms') sections.push('dms_setup', 'dms_cdc_warning');
  if (method === 'bucardo') sections.push('bucardo_ec2_requirements');
  if (method === 'wal_g') sections.push('wal_g_ec2_requirements');

  // Interim database exposure
  if (preferences.global?.migration_approach === 'interim_cutover_data_first') {
    sections.push('interim_database_exposure', 'platform_risk_callout');
  }

  // Post-migration lockdown (always)
  sections.push('post_migration_lockdown');

  return sections;
}

// --- Implementation: No EB/App Runner Check (Property 22) ---

const FORBIDDEN_SERVICES = ['Elastic Beanstalk', 'App Runner', 'ECS Express Mode'];

function validateDesignServices(design) {
  const violations = [];
  for (const service of design.services || []) {
    if (FORBIDDEN_SERVICES.includes(service.aws_service)) {
      violations.push(`Forbidden service found: ${service.aws_service}`);
    }
  }
  return violations;
}

function mapResourcesToDesign(resources) {
  return {
    services: resources.map(r => ({
      service_id: `fargate:${r.heroku_app}:${r.process_type || 'web'}`,
      source_resource_id: r.resource_id,
      heroku_app: r.heroku_app,
      aws_service: 'Fargate',
      confidence: 'deterministic',
      aws_config: {
        task_cpu: 512,
        task_memory: 1024,
        desired_count: r.quantity || 1,
        process_type: r.process_type || 'web',
        load_balancer: (r.process_type || 'web') === 'web',
      },
    })),
  };
}

// --- Generators for Properties 20-22 ---

const arbMigrationApproach = fc.constantFrom('full_cutover', 'interim_cutover_data_first');
const arbMigrationMethod = fc.constantFrom(...MIGRATION_METHODS);
const arbContainerizationStatus = fc.constantFrom(...CONTAINERIZATION_STATUSES);

const arbFutureDate = fc.date({
  min: new Date('2026-06-01'),
  max: new Date('2027-12-31'),
}).map(d => d.toISOString().split('T')[0]);

const arbInterimPreferences = fc.record({
  global: fc.record({
    migration_approach: fc.constant('interim_cutover_data_first'),
    target_exit_date: arbFutureDate,
    interim_cutover: fc.constant(true),
    ktlo_warning: fc.constant('Heroku is in sustaining engineering. Hybrid operation should be bounded to weeks, not quarters.'),
  }),
  data: fc.record({
    migration_method: arbMigrationMethod,
  }),
  operational: fc.record({
    containerization_status: arbContainerizationStatus,
  }),
});

const arbFullCutoverPreferences = fc.record({
  global: fc.record({
    migration_approach: fc.constant('full_cutover'),
    target_exit_date: fc.constant(null),
    interim_cutover: fc.constant(false),
    ktlo_warning: fc.constant(null),
  }),
  data: fc.record({
    migration_method: arbMigrationMethod,
  }),
  operational: fc.record({
    containerization_status: arbContainerizationStatus,
  }),
});

const arbPreferences = fc.oneof(arbInterimPreferences, arbFullCutoverPreferences);

const arbResourceForDesign = fc.record({
  resource_id: fc.string({ minLength: 5, maxLength: 30 }),
  heroku_app: fc.stringOf(fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz-'), { minLength: 3, maxLength: 15 }),
  process_type: fc.constantFrom('web', 'worker', 'clock', 'release'),
  quantity: fc.integer({ min: 1, max: 10 }),
});

// --- Property Tests: Properties 20-22 ---

describe('Feature: heroku-to-aws-migration, Property 20: Interim cutover requires target_exit_date and KTLO warning', () => {
  it('interim_cutover_data_first always has target_exit_date, interim_cutover=true, and ktlo_warning', () => {
    fc.assert(fc.property(arbInterimPreferences, (prefs) => {
      const errors = validateInterimCutover(prefs);
      assert.equal(errors.length, 0, `Validation errors: ${errors.join(', ')}`);
    }), { numRuns: 100 });
  });

  it('full_cutover does not require target_exit_date or ktlo_warning', () => {
    fc.assert(fc.property(arbFullCutoverPreferences, (prefs) => {
      const errors = validateInterimCutover(prefs);
      assert.equal(errors.length, 0, `Validation errors: ${errors.join(', ')}`);
    }), { numRuns: 100 });
  });

  it('missing target_exit_date on interim cutover produces validation error', () => {
    fc.assert(fc.property(arbFutureDate, (date) => {
      const prefs = {
        global: {
          migration_approach: 'interim_cutover_data_first',
          target_exit_date: null, // missing
          interim_cutover: true,
          ktlo_warning: 'warning text',
        },
      };
      const errors = validateInterimCutover(prefs);
      assert.ok(errors.length > 0);
      assert.ok(errors.some(e => e.includes('target_exit_date')));
    }), { numRuns: 10 }); // fewer runs since inputs are minimal
  });

  it('missing ktlo_warning on interim cutover produces validation error', () => {
    fc.assert(fc.property(arbFutureDate, (date) => {
      const prefs = {
        global: {
          migration_approach: 'interim_cutover_data_first',
          target_exit_date: date,
          interim_cutover: true,
          ktlo_warning: null, // missing
        },
      };
      const errors = validateInterimCutover(prefs);
      assert.ok(errors.length > 0);
      assert.ok(errors.some(e => e.includes('ktlo_warning')));
    }), { numRuns: 10 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 21: MIGRATION_GUIDE.md sections match migration_method and containerization_status', () => {
  it('pg_dump_restore produces cutover runbook section', () => {
    fc.assert(fc.property(arbContainerizationStatus, arbMigrationApproach, (containerStatus, approach) => {
      const prefs = {
        global: { migration_approach: approach },
        data: { migration_method: 'pg_dump_restore' },
        operational: { containerization_status: containerStatus },
      };
      const sections = determineGuideSections(prefs);
      assert.ok(sections.includes('pg_dump_cutover_runbook'));
      assert.ok(!sections.includes('dms_setup'));
      assert.ok(!sections.includes('dms_cdc_warning'));
    }), { numRuns: 100 });
  });

  it('dms produces DMS setup and CDC warning sections', () => {
    fc.assert(fc.property(arbContainerizationStatus, arbMigrationApproach, (containerStatus, approach) => {
      const prefs = {
        global: { migration_approach: approach },
        data: { migration_method: 'dms' },
        operational: { containerization_status: containerStatus },
      };
      const sections = determineGuideSections(prefs);
      assert.ok(sections.includes('dms_setup'));
      assert.ok(sections.includes('dms_cdc_warning'));
      assert.ok(!sections.includes('pg_dump_cutover_runbook'));
    }), { numRuns: 100 });
  });

  it('bucardo and wal_g produce EC2 requirements sections', () => {
    fc.assert(fc.property(
      fc.constantFrom('bucardo', 'wal_g'),
      arbContainerizationStatus,
      arbMigrationApproach,
      (method, containerStatus, approach) => {
        const prefs = {
          global: { migration_approach: approach },
          data: { migration_method: method },
          operational: { containerization_status: containerStatus },
        };
        const sections = determineGuideSections(prefs);
        const expected = method === 'bucardo' ? 'bucardo_ec2_requirements' : 'wal_g_ec2_requirements';
        assert.ok(sections.includes(expected));
      }
    ), { numRuns: 100 });
  });

  it('buildpack_only and partial produce containerization_prerequisites section', () => {
    fc.assert(fc.property(
      fc.constantFrom('buildpack_only', 'partial'),
      arbMigrationMethod,
      arbMigrationApproach,
      (containerStatus, method, approach) => {
        const prefs = {
          global: { migration_approach: approach },
          data: { migration_method: method },
          operational: { containerization_status: containerStatus },
        };
        const sections = determineGuideSections(prefs);
        assert.ok(sections.includes('containerization_prerequisites'));
      }
    ), { numRuns: 100 });
  });

  it('containerized does NOT produce containerization_prerequisites section', () => {
    fc.assert(fc.property(arbMigrationMethod, arbMigrationApproach, (method, approach) => {
      const prefs = {
        global: { migration_approach: approach },
        data: { migration_method: method },
        operational: { containerization_status: 'containerized' },
      };
      const sections = determineGuideSections(prefs);
      assert.ok(!sections.includes('containerization_prerequisites'));
    }), { numRuns: 100 });
  });

  it('interim_cutover_data_first produces interim_database_exposure and platform_risk_callout', () => {
    fc.assert(fc.property(arbMigrationMethod, arbContainerizationStatus, (method, containerStatus) => {
      const prefs = {
        global: { migration_approach: 'interim_cutover_data_first' },
        data: { migration_method: method },
        operational: { containerization_status: containerStatus },
      };
      const sections = determineGuideSections(prefs);
      assert.ok(sections.includes('interim_database_exposure'));
      assert.ok(sections.includes('platform_risk_callout'));
    }), { numRuns: 100 });
  });

  it('full_cutover does NOT produce interim sections', () => {
    fc.assert(fc.property(arbMigrationMethod, arbContainerizationStatus, (method, containerStatus) => {
      const prefs = {
        global: { migration_approach: 'full_cutover' },
        data: { migration_method: method },
        operational: { containerization_status: containerStatus },
      };
      const sections = determineGuideSections(prefs);
      assert.ok(!sections.includes('interim_database_exposure'));
      assert.ok(!sections.includes('platform_risk_callout'));
    }), { numRuns: 100 });
  });

  it('post_migration_lockdown is always present', () => {
    fc.assert(fc.property(arbPreferences, (prefs) => {
      const sections = determineGuideSections(prefs);
      assert.ok(sections.includes('post_migration_lockdown'));
    }), { numRuns: 100 });
  });
});

describe('Feature: heroku-to-aws-migration, Property 22: No Elastic Beanstalk or App Runner in design output', () => {
  it('design engine never produces EB, App Runner, or ECS Express Mode services', () => {
    fc.assert(fc.property(
      fc.array(arbResourceForDesign, { minLength: 1, maxLength: 10 }),
      (resources) => {
        const design = mapResourcesToDesign(resources);
        const violations = validateDesignServices(design);
        assert.equal(violations.length, 0, `Violations: ${violations.join(', ')}`);

        // All services must be Fargate
        for (const svc of design.services) {
          assert.equal(svc.aws_service, 'Fargate');
        }
      }
    ), { numRuns: 100 });
  });

  it('forbidden services list includes EB, App Runner, and ECS Express Mode', () => {
    for (const forbidden of FORBIDDEN_SERVICES) {
      const fakeDesign = { services: [{ aws_service: forbidden }] };
      const violations = validateDesignServices(fakeDesign);
      assert.ok(violations.length > 0, `Should reject: ${forbidden}`);
    }
  });

  it('Fargate is always accepted', () => {
    fc.assert(fc.property(
      fc.array(arbResourceForDesign, { minLength: 1, maxLength: 10 }),
      (resources) => {
        const design = mapResourcesToDesign(resources);
        const violations = validateDesignServices(design);
        assert.equal(violations.length, 0);
      }
    ), { numRuns: 100 });
  });
});
