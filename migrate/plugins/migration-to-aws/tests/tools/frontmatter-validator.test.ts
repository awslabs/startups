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
    // A partial-rollout stub: 'clarify' is a REAL downstream phase whose file
    // exists but carries NO frontmatter yet (mid phase-by-phase rollout). It is
    // invisible to the typed model (bindSkill skips no-frontmatter files) but makes
    // discover's `_advances_to: clarify` resolve on disk — so the dangling-edge
    // check tolerates it (a real phase, not a typo).
    'references/phases/clarify/clarify.md':
`# Clarify

prose-only phase (no frontmatter yet).
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
    // goodSkill includes a frontmatter-less clarify.md stub — a real phase mid-
    // rollout. discover._advances_to: clarify must resolve (dir exists) and NOT be
    // flagged as dangling, even though clarify has no typed frontmatter yet.
    const findings = validateFixture(goodSkill());
    assert.ok(
      !findings.some((f) => /advances_to|clarify/.test(f.message)),
      'should not fail on an unverifiable forward reference',
    );
  });

  it('rejects an _advances_to that names a phase with no file on disk (dangling forward edge)', () => {
    const files = goodSkill();
    // Point discover at a phase that does not exist at all (a typo, not rollout).
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_advances_to: clarify', '_advances_to: clarify_TYPO');
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /_advances_to 'clarify_TYPO' names neither a terminal.*nor an existing phase.*dangling forward edge/s,
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

  // ---- entry phase: _init uniqueness + _init ⟺ backbone head ----

  it('accepts a single _init phase that is the backbone head', () => {
    // chainSkill: discover has _init:true and no _requires_phase (the head).
    const findings = validateFixture(chainSkill());
    assert.equal(findings.length, 0, `expected no findings, got: ${JSON.stringify(findings)}`);
  });

  it('rejects two phases both declaring _init: true', () => {
    const files = chainSkill();
    // Give clarify _init too (now discover AND clarify both claim the entry).
    files['references/phases/clarify/clarify.md'] = files[
      'references/phases/clarify/clarify.md'
    ].replace('_requires_phase: discover', '_init: true\n_requires_phase: discover');
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /multiple phases declare '_init: true'/);
  });

  it('rejects an _init phase that also declares _requires_phase (entry must be the head)', () => {
    const files = chainSkill();
    // Move _init off the head: strip it from discover, add it to clarify (which
    // has a _requires_phase) so _init and 'no _requires_phase' no longer coincide.
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_init: true\n', '');
    files['references/phases/clarify/clarify.md'] = files[
      'references/phases/clarify/clarify.md'
    ].replace('_requires_phase: discover', '_init: true\n_requires_phase: discover');
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /entry phase 'clarify' declares '_init: true' but also '_requires_phase: discover'/,
    );
  });

  it('rejects a checkpoint phase declaring _init: true (entry must be backbone)', () => {
    const files = chainSkill();
    // Strip _init from discover; put it on the feedback checkpoint.
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_init: true\n', '');
    files['references/phases/feedback/feedback.md'] = files[
      'references/phases/feedback/feedback.md'
    ].replace('_kind: checkpoint', '_kind: checkpoint\n_init: true');
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /checkpoint phase 'feedback' declares '_init: true'/,
    );
  });

  it('rejects a fully-declared backbone with no _init entry phase', () => {
    const files = chainSkill();
    // Remove the only _init: the backbone (discover->clarify) now has no entry.
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_init: true\n', '');
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /no phase declares '_init: true'/,
    );
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

  // ---- conditional artifacts in _produces / _contributes ({file, _when}) ----

  it('accepts a conditional _produces entry ({file, _when}) with a matching fragment creator', () => {
    // discover produces inventory.json (assembler). Add a CONDITIONAL artifact the
    // terraform fragment contributes, so single-creator is satisfied.
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace(
      '_produces:\n  - inventory.json',
      '_produces:\n  - inventory.json\n  - { file: eks.tf, _when: "EKS in design" }',
    );
    files['references/phases/discover/discover-terraform.md'] = files[
      'references/phases/discover/discover-terraform.md'
    ].replace(
      '_contributes:\n  - inventory.json (resource entries)',
      '_contributes:\n  - inventory.json (resource entries)\n  - { file: eks.tf, _when: "EKS in design" }',
    );
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected no findings, got: ${JSON.stringify(findings)}`);
  });

  it('rejects a conditional artifact map with no parseable file: (malformed)', () => {
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace(
      '_produces:\n  - inventory.json',
      '_produces:\n  - inventory.json\n  - { _when: "EKS in design" }',
    );
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /_produces has a conditional entry with no parseable 'file:'/,
    );
  });

  it('applies single-creator to a conditional _produces artifact (uncreated -> flagged)', () => {
    // Declare a conditional artifact in _produces that NO fragment contributes and
    // the assembler does not produce -> single-creator must still flag it.
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace(
      '_produces:\n  - inventory.json',
      '_produces:\n  - inventory.json\n  - { file: orphan-eks.tf, _when: "EKS in design" }',
    );
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /phase _produces 'orphan-eks\.tf' but no unit creates it/,
    );
  });

  it('accepts a trailing-slash directory as a conditional artifact (kubernetes/)', () => {
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace(
      '_produces:\n  - inventory.json',
      '_produces:\n  - inventory.json\n  - { file: kubernetes/, _when: "EKS in design" }',
    );
    files['references/phases/discover/discover-terraform.md'] = files[
      'references/phases/discover/discover-terraform.md'
    ].replace(
      '_contributes:\n  - inventory.json (resource entries)',
      '_contributes:\n  - inventory.json (resource entries)\n  - { file: kubernetes/, _when: "EKS in design" }',
    );
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected no findings, got: ${JSON.stringify(findings)}`);
  });

  // ---- _exec (execution mode / agent dispatch) ----
  //
  // A dispatched phase must (a) name a valid capability tier, (b) name a tier whose
  // generic-phase-worker-<tier>.md is shipped under the plugin's agents/ dir, and
  // (c) explicitly declare its work non-interactive. The fixture skill root is the
  // tmp dir itself, so a `agents/generic-phase-worker-<tier>.md` entry in the files
  // map lands where discoverWorkerTiers() finds it. When NO agents/ dir is present
  // the worker-exists check is UNVERIFIED (null) and skipped — so reject-tests that
  // target a DIFFERENT rule omit agents/ to keep only their target rule firing.

  // A shipped worker file for a tier (its body is irrelevant to the validator).
  const worker = (tier: string): [string, string] => [
    `agents/generic-phase-worker-${tier}.md`,
    `---\nname: generic-phase-worker-${tier}\n---\nworker\n`,
  ];
  // Add `_exec` (+ the required `_interactive: false`) to goodSkill's discover phase.
  const withExec = (files: Record<string, string>, execFrag: string, interactive = '\n_interactive: false') => {
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_advances_to: clarify', `_advances_to: clarify${interactive}\n${execFrag}`);
    return files;
  };

  it('accepts a phase with _exec: { _agent: rw }, _interactive: false, and the rw worker shipped', () => {
    // goodSkill's discover _produces inventory.json -> rw is the derived minimum.
    const files = withExec(goodSkill(), '_exec: { _agent: rw }');
    const [wp, wc] = worker('rw');
    files[wp] = wc;
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('accepts an _exec in nested block form (_agent: git) when the git worker is shipped', () => {
    const files = withExec(goodSkill(), '_exec:\n  _agent: git');
    const [wp, wc] = worker('git');
    files[wp] = wc;
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  it('rejects an _exec._agent that is not a recognized tier', () => {
    const files = withExec(goodSkill(), '_exec: { _agent: superuser }');
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /_exec\._agent 'superuser' is not a recognized capability tier/,
    );
  });

  it('rejects an unknown _exec sub-key (typo)', () => {
    const files = withExec(goodSkill(), '_exec: { _agent: rw, _agnet: rw }');
    const [wp, wc] = worker('rw');
    files[wp] = wc;
    const findings = validateFixture(files);
    assert.match(findings.map((f) => f.message).join('\n'), /unknown _exec sub-key '_agnet'/);
  });

  it('rejects _exec present with no _agent tier', () => {
    const files = withExec(goodSkill(), '_exec:\n  _mode: agent');
    const findings = validateFixture(files);
    const msg = findings.map((f) => f.message).join('\n');
    assert.match(msg, /_exec is present but declares no _agent tier/);
    assert.match(msg, /unknown _exec sub-key '_mode'/);
  });

  it('rejects _agent: ro on a producing phase (derived-minimum tier)', () => {
    // discover _produces inventory.json, so ro (read-only) is below the minimum.
    const files = withExec(goodSkill(), '_exec: { _agent: ro }');
    const [wp, wc] = worker('ro');
    files[wp] = wc;
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /_exec\._agent 'ro' \(read-only\) but phase 'discover' _produces .* needs at least 'rw'/,
    );
  });

  it('rejects _exec on a fragment (one-level rule: _exec is phase-only)', () => {
    // A fragment carrying _exec must trip the closed-vocab check — nested dispatch
    // is structurally unrepresentable.
    const files = goodSkill();
    files['references/phases/discover/discover-terraform.md'] = files[
      'references/phases/discover/discover-terraform.md'
    ].replace('_of_phase: discover', '_of_phase: discover\n_exec: { _agent: rw }');
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /unknown fragment frontmatter key '_exec'/,
    );
  });

  // ---- _exec ⟹ _interactive: false (dispatch requires an explicit non-interactive affirmation) ----

  it('rejects _exec on a phase with NO _interactive declaration', () => {
    // withExec but pass an empty interactive prefix -> the affirmation is absent.
    const files = withExec(goodSkill(), '_exec: { _agent: rw }', '');
    const [wp, wc] = worker('rw');
    files[wp] = wc;
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /declares _exec but no _interactive declaration .* MUST declare '_interactive: false'/,
    );
  });

  it('rejects _exec on a phase declared _interactive: true', () => {
    const files = withExec(goodSkill(), '_exec: { _agent: rw }', '\n_interactive: true');
    const [wp, wc] = worker('rw');
    files[wp] = wc;
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /declares _exec but _interactive: true .* non-interactive work can be dispatched/,
    );
  });

  it('accepts _interactive: false on a NON-_exec phase (the affirmation is harmless without dispatch)', () => {
    const files = goodSkill();
    files['references/phases/discover/discover.md'] = files[
      'references/phases/discover/discover.md'
    ].replace('_advances_to: clarify', '_advances_to: clarify\n_interactive: false');
    const findings = validateFixture(files);
    assert.equal(findings.length, 0, `expected clean, got: ${JSON.stringify(findings)}`);
  });

  // ---- worker-exists (the tier's generic-phase-worker-<tier>.md must be shipped) ----

  it('rejects _exec._agent naming a tier whose worker is not shipped', () => {
    // agents/ exists (rw worker shipped) but the phase asks for git -> no git worker.
    const files = withExec(goodSkill(), '_exec:\n  _agent: git');
    const [wp, wc] = worker('rw'); // only rw shipped, NOT git
    files[wp] = wc;
    const findings = validateFixture(files);
    assert.match(
      findings.map((f) => f.message).join('\n'),
      /_exec\._agent 'git' has no worker on disk .*generic-phase-worker-git\.md/,
    );
  });

  it('does NOT run worker-exists when the plugin agents/ dir is absent (UNVERIFIED)', () => {
    // No agents/ dir in the fixture -> availableWorkerTiers is null -> the check is
    // skipped (tolerant of a skill laid out without the standard plugin structure).
    const files = withExec(goodSkill(), '_exec: { _agent: git }'); // git, but no agents/ dir at all
    const findings = validateFixture(files);
    assert.equal(
      findings.filter((f) => /has no worker on disk/.test(f.message)).length,
      0,
      `worker-exists should be skipped, got: ${JSON.stringify(findings)}`,
    );
  });
});
