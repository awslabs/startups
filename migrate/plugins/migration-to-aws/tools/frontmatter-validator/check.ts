// check.ts — structural checks over the typed frontmatter. Skill-AGNOSTIC: every
// check is a property of the phase/fragment/assembler grammar (INTERPRETER.md),
// not of any particular skill. The valid phase set is DERIVED from the phase files
// that declare frontmatter (never hardcoded); references to phases that don't yet
// carry frontmatter are left UNVERIFIED rather than failed (tolerant of a
// phase-by-phase rollout).

import type {
  AssemblerFrontmatter,
  Finding,
  FragmentFrontmatter,
  PhaseFrontmatter,
} from "./types.ts";
import { existsSync } from "node:fs";
import { join } from "node:path";

export interface BoundSkill {
  /** absolute path to the skill's `references/` root (where phase _file paths resolve). */
  referencesRoot: string;
  phases: PhaseFrontmatter[];
  fragments: Map<string, FragmentFrontmatter>; // by resolved absolute path
  assemblers: Map<string, AssemblerFrontmatter>; // by resolved absolute path
  rel: (absPath: string) => string; // for readable messages
}

export function check(skill: BoundSkill): Finding[] {
  const findings: Finding[] = [];
  const add = (file: string, message: string) => findings.push({ file, message });

  // Derived phase set: only phases that declare frontmatter.
  const declaredPhases = new Set(skill.phases.map((p) => p.phase).filter(Boolean));
  const TERMINALS = new Set(["complete", "done", "end"]);

  for (const phase of skill.phases) {
    const pf = skill.rel(phase.sourceFile);

    // closed vocab
    for (const k of phase.unknownKeys) add(pf, `unknown phase frontmatter key '${k}'`);

    // _advances_to / _requires_phase: verify only when the target declares frontmatter;
    // otherwise UNVERIFIED (skip) — tolerant of partial rollout.
    if (phase.advancesTo && !TERMINALS.has(phase.advancesTo) && !declaredPhases.has(phase.advancesTo)) {
      // unverified — target phase has no frontmatter yet. no finding.
    }
    if (phase.requiresPhase && declaredPhases.size > 1 && !declaredPhases.has(phase.requiresPhase)) {
      // unverified likewise. no finding.
    }

    // fragments
    for (const fr of phase.fragments) {
      if (fr.trigger.kind === "unknown") {
        add(pf, `fragment '${fr.id}' has an unrecognized _trigger form: ${fr.trigger.raw}`);
      }
      const fpath = join(skill.referencesRoot, fr.file);
      if (!existsSync(fpath)) {
        add(pf, `fragment '${fr.id}' _file does not resolve: ${fr.file}`);
        continue;
      }
      const frag = skill.fragments.get(fpath);
      if (!frag) {
        add(skill.rel(fpath), `referenced as a fragment by '${phase.phase}' but has no fragment frontmatter`);
        continue;
      }
      for (const k of frag.unknownKeys) add(skill.rel(fpath), `unknown fragment frontmatter key '${k}'`);
      if (frag.fragment !== fr.id) {
        add(skill.rel(fpath), `_fragment id '${frag.fragment || "(missing)"}' != phase reference _id '${fr.id}'`);
      }
      if (frag.ofPhase !== phase.phase) {
        add(skill.rel(fpath), `_of_phase '${frag.ofPhase || "(missing)"}' != '${phase.phase}'`);
      }
    }

    // assembler: exactly one, resolves, back-references, single-creator ownership
    if (!phase.assembleFile) {
      add(pf, `missing _assemble._file (a phase must have exactly one assembler)`);
      continue;
    }
    const apath = join(skill.referencesRoot, phase.assembleFile);
    if (!existsSync(apath)) {
      add(pf, `_assemble._file does not resolve: ${phase.assembleFile}`);
      continue;
    }
    const asm = skill.assemblers.get(apath);
    if (!asm) {
      add(skill.rel(apath), `referenced as the assembler by '${phase.phase}' but has no assembler frontmatter`);
      continue;
    }
    for (const k of asm.unknownKeys) add(skill.rel(apath), `unknown assembler frontmatter key '${k}'`);
    if (asm.ofPhase !== phase.phase) {
      add(skill.rel(apath), `_of_phase '${asm.ofPhase || "(missing)"}' != '${phase.phase}'`);
    }
    // single-creator: everything the phase _produces must be created by the assembler.
    for (const art of phase.produces) {
      if (!asm.produces.includes(art)) {
        add(pf, `phase _produces '${art}' but the assembler does not declare it in _produces (single-creator rule)`);
      }
    }
  }

  return findings;
}
