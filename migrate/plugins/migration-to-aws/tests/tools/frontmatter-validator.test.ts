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
});
