// validate.ts — orchestrator + CLI. Discovers the phase files of a skill, binds
// their frontmatter (+ referenced fragments/assemblers) into the typed model, runs
// the structural checks, reports, and exits non-zero on any finding.
//
// Usage: node validate.ts <skill-root>
//   where <skill-root> contains references/phases/<name>/<name>.md
//
// Skill-agnostic: it knows the phase/fragment/assembler grammar, not any skill.

import type { Finding } from "./types.ts";
import { type BoundSkill, check } from "./check.ts";
import {
  extractFrontmatter,
  parseAssembler,
  parseFragment,
  parsePhase,
} from "./parse.ts";
import { existsSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

/** Bind a skill root into the typed model (exported so tests can reuse it). */
export function bindSkill(skillRoot: string): BoundSkill {
  const referencesRoot = join(skillRoot, "references");
  const phasesDir = join(referencesRoot, "phases");
  const rel = (abs: string) => abs.replace(skillRoot + "/", "");

  const phases: BoundSkill["phases"] = [];
  const fragments: BoundSkill["fragments"] = new Map();
  const assemblers: BoundSkill["assemblers"] = new Map();

  if (!existsSync(phasesDir)) {
    return { referencesRoot, phases, fragments, assemblers, rel };
  }

  const phaseNames = readdirSync(phasesDir).filter((d) =>
    statSync(join(phasesDir, d)).isDirectory()
  );

  for (const name of phaseNames) {
    const phaseFile = join(phasesDir, name, `${name}.md`);
    if (!existsSync(phaseFile)) continue;
    const fm = extractFrontmatter(phaseFile);
    if (!fm) continue; // no frontmatter yet — skip (phase-by-phase rollout)
    const phase = parsePhase(phaseFile, fm);
    phases.push(phase);

    // bind referenced fragments
    for (const fr of phase.fragments) {
      const fpath = join(referencesRoot, fr.file);
      if (existsSync(fpath) && !fragments.has(fpath)) {
        const ffm = extractFrontmatter(fpath);
        if (ffm) fragments.set(fpath, parseFragment(fpath, ffm));
      }
    }
    // bind the assembler
    if (phase.assembleFile) {
      const apath = join(referencesRoot, phase.assembleFile);
      if (existsSync(apath) && !assemblers.has(apath)) {
        const afm = extractFrontmatter(apath);
        if (afm) assemblers.set(apath, parseAssembler(apath, afm));
      }
    }
  }

  return { referencesRoot, phases, fragments, assemblers, rel };
}

/** Validate a skill root; returns findings (empty = clean). Exported for tests. */
export function validateSkill(skillRoot: string): Finding[] {
  return check(bindSkill(resolve(skillRoot)));
}

// --- CLI ---
// Run only when invoked directly (not when imported by the test).
const invokedPath = process.argv[1] ?? "";
if (invokedPath.endsWith("validate.ts")) {
  const skillRoot = process.argv[2];
  if (!skillRoot) {
    console.error("usage: node validate.ts <skill-root>");
    process.exit(2);
  }
  const findings = validateSkill(skillRoot);
  if (findings.length) {
    console.error(`frontmatter validation: ${findings.length} problem(s)`);
    for (const f of findings) console.error(`  - ${f.file}: ${f.message}`);
    process.exit(1);
  }
  const boundPhases = bindSkill(resolve(skillRoot)).phases.length;
  console.log(`frontmatter validation: OK (${boundPhases} phase file(s) with frontmatter checked)`);
}
