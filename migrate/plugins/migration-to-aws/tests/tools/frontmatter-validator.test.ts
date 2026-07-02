// Tests for the skill-agnostic frontmatter validator (tools/frontmatter-validator).
//
// The "guard on the guard": feed the validator KNOWN-GOOD and KNOWN-BAD frontmatter
// (as ephemeral fixture skills in a temp dir) and assert it accepts the good and
// rejects each bad variant. The bad frontmatter lives ONLY here as fixtures — it
// never touches a real skill or git history. If someone breaks the validator so it
// stops catching a bad edit, these tests go red.
//
// Run: node --test tests/tools/frontmatter-validator.test.ts
//
// (TypeScript, imports the TypeScript validator; run via Node 24 type-stripping.)

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { validateSkill } from '../../tools/frontmatter-validator/validate.ts';
import type { Finding } from '../../tools/frontmatter-validator/types.ts';

// Build an ephemeral skill on disk from a map of {relativePath: contents}, run the
// validator against it, and clean up.
function validateFixture(files: Record<string, string>): Finding[] {
  const root = mkdtempSync(join(tmpdir(), 'fm-fixture-'));
  try {
    for (const [rel, contents] of Object.entries(files)) {
      const abs = join(root, rel);
      mkdirSync(abs.slice(0, abs.lastIndexOf('/')), { recursive: true });
      writeFileSync(abs, contents);
    }
    return validateSkill(root);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

// A minimal, VALID single-phase skill: phase + 1 fragment + assembler.
function goodSkill(): Record<string, string> {
  return {
    'references/phases/discover/discover.md':
`---
_phase: discover
_title: "Discover"
_init: true
_input: workspace
_fragments:
  - _id: terraform
    _trigger: { _always: true }
    _file: phases/discover/discover-terraform.md
_assemble:
  _file: phases/discover/discover-assemble.md
_produces:
  - inventory.json
_advances_to: clarify
---
# Discover
prose body.
`,
    'references/phases/discover/discover-terraform.md':
`---
_fragment: terraform
_of_phase: discover
_contributes:
  - inventory.json (resource entries)
---
# Terraform fragment
prose body.
`,
    'references/phases/discover/discover-assemble.md':
`---
_assemble: assemble-inventory
_of_phase: discover
_reads:
  - terraform
_produces:
  - inventory.json
---
# Assembler
prose body.
`,
  };
}

describe('frontmatter-validator', () => {
  it('accepts a well-formed phase/fragment/assembler skill', () => {
    const findings = validateFixture(goodSkill());
    assert.equal(findings.length, 0, `expected no findings, got: ${JSON.stringify(findings)}`);
  });

  it('rejects a phase _fragments._file that does not resolve', () => {
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('discover-terraform.md', 'discover-MISSING.md');
    const findings = validateFixture(files);
    assert.ok(findings.length >= 1, 'expected a finding for the unresolved _file');
    assert.match(findings.map((f) => f.message).join('\n'), /_file does not resolve/);
  });

  it("rejects an unknown (typo'd) frontmatter key", () => {
    const files = goodSkill();
    files['references/phases/discover/discover-terraform.md'] = files[
      'references/phases/discover/discover-terraform.md'
    ].replace('_fragment:', '_fragmnet:');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /unknown fragment frontmatter key '_fragmnet'/);
  });

  it("rejects a fragment whose _fragment id != the phase's reference _id", () => {
    const files = goodSkill();
    files['references/phases/discover/discover-terraform.md'] = files[
      'references/phases/discover/discover-terraform.md'
    ].replace('_fragment: terraform', '_fragment: terraformX');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /_fragment id 'terraformX' != phase reference _id 'terraform'/);
  });

  it('rejects an unrecognized _trigger form', () => {
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('{ _always: true }', '{ _whenever: true }');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /unrecognized _trigger form/);
  });

  it('accepts a _when trigger (opaque prose condition, not evaluated by CI)', () => {
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('{ _always: true }', `{ _when: "preferences.foo.value is 'bar'" }`);
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected _when to be accepted, got: ${JSON.stringify(findings)}`);
  });

  it('rejects a phase _produces artifact the assembler does not create (single-creator)', () => {
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('  - inventory.json\n_advances_to', '  - inventory.json\n  - orphan.json\n_advances_to');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /single-creator rule/);
  });

  it('rejects an artifact created by two fragments with no assembler owner (ambiguous creator)', () => {
    const files = goodSkill();
    // add a second fragment; both fragments create doc.json; doc.json is in _produces
    // but NOT in the assembler _produces → two fragment creators, no assembler owner.
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ]
      .replace(
        '    _file: phases/discover/discover-terraform.md',
        '    _file: phases/discover/discover-terraform.md\n  - _id: docs\n    _trigger: { _always: true }\n    _file: phases/discover/discover-docs.md',
      )
      .replace('  - inventory.json\n_advances_to', '  - inventory.json\n  - doc.json\n_advances_to');
    files['references/phases/discover/discover-terraform.md'] = files[
      'references/phases/discover/discover-terraform.md'
    ].replace('  - inventory.json (resource entries)', '  - doc.json');
    files['references/phases/discover/discover-docs.md'] =
`---
_fragment: docs
_of_phase: discover
_contributes:
  - doc.json
---
# Docs fragment
`;
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /ambiguous creator/);
  });

  it('does NOT fail an _advances_to that points at a phase without frontmatter (partial rollout)', () => {
    const findings = validateFixture(goodSkill());
    assert.ok(
      !findings.some((f) => /advances_to|clarify/.test(f.message)),
      'should not fail on an unverifiable forward reference',
    );
  });

  // ---- backbone / checkpoint + chain-consistency ----

  // A fully-declared 2-phase backbone (discover -> clarify -> complete) plus a
  // feedback CHECKPOINT (off-backbone, trigger-entered). Minimal but complete.
  function chainSkill(): Record<string, string> {
    const phase = (name: string, extra: string, frag = name, assemble = name) => ({
      [`references/phases/${name}/${name}.md`]:
`---
_phase: ${name}
_title: "${name}"
${extra}
_fragments:
  - _id: ${frag}
    _trigger: { _always: true }
    _file: phases/${name}/${name}-frag.md
_assemble:
  _file: phases/${name}/${name}-asm.md
_produces:
  - ${name}.json
---
# ${name}
`,
      [`references/phases/${name}/${name}-frag.md`]:
`---
_fragment: ${frag}
_of_phase: ${name}
_contributes:
  - ${name}.json
---
# frag
`,
      [`references/phases/${name}/${name}-asm.md`]:
`---
_assemble: asm-${name}
_of_phase: ${name}
_reads:
  - ${frag}
_produces:
  - ${name}.json
---
# asm
`,
    });
    return {
      ...phase('discover', '_init: true\n_advances_to: clarify'),
      ...phase('clarify', '_requires_phase: discover\n_advances_to: complete'),
      ...phase(
        'feedback',
        '_kind: checkpoint\n_requires_phase: discover\n_trigger: { _when: "user opts in" }',
      ),
    };
  }

  it('accepts a valid backbone + a checkpoint phase', () => {
    const findings = validateFixture(chainSkill());
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('rejects a checkpoint phase that declares _advances_to (must be off-backbone)', () => {
    const files = chainSkill();
    files['references/phases/feedback/feedback.md'] = files[
      'references/phases/feedback/feedback.md'
    ].replace('_trigger: { _when: "user opts in" }', '_trigger: { _when: "user opts in" }\n_advances_to: complete');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /checkpoint phase 'feedback' must NOT declare _advances_to/);
  });

  it('rejects a checkpoint phase with no phase-level _trigger', () => {
    const files = chainSkill();
    files['references/phases/feedback/feedback.md'] = files[
      'references/phases/feedback/feedback.md'
    ].replace('\n_trigger: { _when: "user opts in" }', '');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /checkpoint phase 'feedback' must declare a phase-level _trigger/);
  });

  it('rejects a backbone phase that declares a phase-level _trigger', () => {
    const files = chainSkill();
    files['references/phases/clarify/clarify.md'] = files[
      'references/phases/clarify/clarify.md'
    ].replace('_requires_phase: discover', '_requires_phase: discover\n_trigger: { _when: "x" }');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /backbone phase 'clarify' must NOT declare a phase-level _trigger/);
  });

  it('rejects a backbone phase missing _advances_to', () => {
    const files = chainSkill();
    files['references/phases/clarify/clarify.md'] = files[
      'references/phases/clarify/clarify.md'
    ].replace('\n_advances_to: complete', '');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /backbone phase 'clarify' must declare _advances_to/);
  });

  it('rejects a chain inconsistency (forward edge with no matching back-link)', () => {
    const files = chainSkill();
    // discover advances to clarify, but make clarify require the wrong predecessor.
    files['references/phases/clarify/clarify.md'] = files[
      'references/phases/clarify/clarify.md'
    ].replace('_requires_phase: discover', '_requires_phase: feedback');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /chain inconsistency/);
  });

  // ---- _re_entry_guard ----

  // discover guards its downstream (clarify); clarify's _produces is 'clarify.json'.
  const GOOD_GUARD =
    '_re_entry_guard:\n' +
    '  _stale_if_completed: clarify\n' +
    '  _stale_artifact: clarify.json\n' +
    '  _on_reentry: stop_unless_confirmed\n' +
    '  _on_confirm: reset_downstream_to_pending';

  function guardOnDiscover(guard: string): Record<string, string> {
    const files = chainSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_advances_to: clarify', `_advances_to: clarify\n${guard}`);
    return files;
  }

  it('accepts a well-formed _re_entry_guard', () => {
    const findings = validateFixture(guardOnDiscover(GOOD_GUARD));
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('rejects an unknown _re_entry_guard sub-key (typo)', () => {
    const findings = validateFixture(
      guardOnDiscover(GOOD_GUARD.replace('_stale_artifact:', '_stale_artifcat:')),
    );
    const msg = findings.map((f) => f.message).join('\n');
    assert.match(msg, /unknown _re_entry_guard sub-key '_stale_artifcat'/);
  });

  it('rejects a _re_entry_guard missing a required sub-key', () => {
    const findings = validateFixture(
      guardOnDiscover(
        '_re_entry_guard:\n' +
        '  _stale_if_completed: clarify\n' +
        '  _stale_artifact: clarify.json\n' +
        '  _on_reentry: stop_unless_confirmed',
      ),
    );
    assert.match(findings.map((f) => f.message).join('\n'), /_re_entry_guard missing _on_confirm/);
  });

  it('rejects a _re_entry_guard with an out-of-vocab enum value', () => {
    const findings = validateFixture(
      guardOnDiscover(GOOD_GUARD.replace('stop_unless_confirmed', 'silently_overwrite')),
    );
    assert.match(findings.map((f) => f.message).join('\n'), /_on_reentry 'silently_overwrite' is not a recognized value/);
  });

  it('rejects a _re_entry_guard whose _stale_if_completed != _advances_to', () => {
    const findings = validateFixture(
      guardOnDiscover(GOOD_GUARD.replace('_stale_if_completed: clarify', '_stale_if_completed: feedback')),
    );
    assert.match(findings.map((f) => f.message).join('\n'), /should equal this phase's _advances_to/);
  });

  it('rejects a _re_entry_guard whose _stale_artifact is not in the downstream _produces (hard fail)', () => {
    const findings = validateFixture(
      guardOnDiscover(GOOD_GUARD.replace('_stale_artifact: clarify.json', '_stale_artifact: wrong.json')),
    );
    assert.match(findings.map((f) => f.message).join('\n'), /is not in the _produces of the downstream phase 'clarify'/);
  });

  it('rejects a _re_entry_guard on a terminal-advancing phase (nothing downstream)', () => {
    // put a guard on clarify, which _advances_to: complete (a terminal)
    const files = chainSkill();
    files['references/phases/clarify/clarify.md'] = files[
      'references/phases/clarify/clarify.md'
    ].replace(
      '_advances_to: complete',
      '_advances_to: complete\n_re_entry_guard:\n  _stale_if_completed: complete\n  _stale_artifact: x.json\n  _on_reentry: stop_unless_confirmed\n  _on_confirm: reset_downstream_to_pending',
    );
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /has a _re_entry_guard but no downstream backbone phase/);
  });

  // ---- _preconditions / _postconditions / _forbids_files ----

  // Attach a gate block to discover (which _produces discover.json in chainSkill).
  function gatesOnDiscover(gates: string): Record<string, string> {
    const files = chainSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_advances_to: clarify', `_advances_to: clarify\n${gates}`);
    return files;
  }

  const GOOD_GATES =
    '_preconditions:\n' +
    '  - _check_single_active_phase: true\n' +
    '    _on_failure: _halt_and_inform\n' +
    '  - _assert: "a heroku_* resource exists"\n' +
    '    _on_failure: _unrecoverable\n' +
    '_postconditions:\n' +
    '  - _check_file_exists: discover.json\n' +
    '    _on_failure: _halt_and_inform\n' +
    '  - _assert: "inventory has at least one resource"\n' +
    '    _on_failure: _halt_and_inform';

  it('accepts well-formed _preconditions / _postconditions', () => {
    const findings = validateFixture(gatesOnDiscover(GOOD_GATES));
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('rejects an unknown check kind', () => {
    const findings = validateFixture(
      gatesOnDiscover(GOOD_GATES.replace('_check_single_active_phase', '_check_vibes')),
    );
    assert.match(findings.map((f) => f.message).join('\n'), /unknown _preconditions check kind '_check_vibes'/);
  });

  it('rejects an unrecognized _on_failure action', () => {
    const findings = validateFixture(
      gatesOnDiscover(GOOD_GATES.replace('_unrecoverable', '_explode')),
    );
    assert.match(findings.map((f) => f.message).join('\n'), /unrecognized _on_failure action '_explode'/);
  });

  it('rejects a _check_phase_completed naming no declared phase', () => {
    const findings = validateFixture(
      gatesOnDiscover(
        '_preconditions:\n  - _check_phase_completed: nonesuch\n    _on_failure: _halt_and_inform',
      ),
    );
    assert.match(findings.map((f) => f.message).join('\n'), /_check_phase_completed 'nonesuch' names no declared phase/);
  });

  it('rejects a _postconditions file-exists not in _produces (finding-#2 cross-check)', () => {
    const findings = validateFixture(
      gatesOnDiscover(
        '_postconditions:\n  - _check_file_exists: not-produced.json\n    _on_failure: _halt_and_inform',
      ),
    );
    assert.match(findings.map((f) => f.message).join('\n'), /_check_file_exists 'not-produced.json' but it is not in this phase's _produces/);
  });

  it('accepts _forbids_files as a glob list', () => {
    const findings = validateFixture(
      gatesOnDiscover('_forbids_files:\n  - README.md\n  - "*.txt"'),
    );
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  // ---- _knowledge + _input resolution ----

  it('accepts _knowledge whose file resolves on disk', () => {
    const files = chainSkill();
    files['knowledge/design/sizing.json'] = '{}';
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_advances_to: clarify', '_advances_to: clarify\n_knowledge:\n  - { file: knowledge/design/sizing.json }');
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('rejects a _knowledge file that does not resolve', () => {
    const files = chainSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_advances_to: clarify', '_advances_to: clarify\n_knowledge:\n  - { file: knowledge/design/MISSING.json }');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /_knowledge file does not resolve: knowledge\/design\/MISSING\.json/);
  });

  it('accepts a _knowledge _when (opaque, not evaluated)', () => {
    const files = chainSkill();
    files['knowledge/x.json'] = '{}';
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_advances_to: clarify', '_advances_to: clarify\n_knowledge:\n  - { file: knowledge/x.json, _when: "inventory has a formation" }');
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('accepts an assembler _knowledge whose file resolves on disk', () => {
    const files = goodSkill();
    files['references/shared/ref.md'] = '# ref';
    files['references/phases/discover/discover-assemble.md'] = files[
      'references/phases/discover/discover-assemble.md'
    ].replace('_produces:\n  - inventory.json', '_knowledge:\n  - { file: references/shared/ref.md }\n_produces:\n  - inventory.json');
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('rejects an assembler _knowledge file that does not resolve', () => {
    const files = goodSkill();
    files['references/phases/discover/discover-assemble.md'] = files[
      'references/phases/discover/discover-assemble.md'
    ].replace('_produces:\n  - inventory.json', '_knowledge:\n  - { file: references/shared/MISSING.md }\n_produces:\n  - inventory.json');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /_knowledge file does not resolve: references\/shared\/MISSING\.md/);
  });

  it('accepts _input resolving to an upstream _produces (and the workspace literal)', () => {
    // chainSkill: discover _input workspace (add it), clarify reads discover.json
    const files = chainSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_init: true', '_init: true\n_input: workspace');
    files['references/phases/clarify/clarify.md'] = files[
      'references/phases/clarify/clarify.md'
    ].replace('_requires_phase: discover', '_requires_phase: discover\n_input:\n  - discover.json');
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('rejects an _input artifact produced by no phase', () => {
    const files = chainSkill();
    files['references/phases/clarify/clarify.md'] = files[
      'references/phases/clarify/clarify.md'
    ].replace('_requires_phase: discover', '_requires_phase: discover\n_input:\n  - nonexistent-artifact.json');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /_input 'nonexistent-artifact\.json' is not produced by any declared phase/);
  });
});
