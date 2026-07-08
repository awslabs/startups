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
import { dirname, join, resolve } from "node:path";

/** The generic-phase-worker file-name prefix (INTERPRETER.md § _exec). A tier `<t>`
 *  is dispatchable only if `agents/generic-phase-worker-<t>.md` is shipped. */
const WORKER_PREFIX = "generic-phase-worker-";

/**
 * Locate the plugin's `agents/` directory and return the set of capability tiers for
 * which a `generic-phase-worker-<tier>.md` file exists, or null if no `agents/` dir is
 * found. The skill lives at `<plugin>/skills/<skill>`, so `agents/` is normally two
 * levels up; we walk up a few levels to tolerate minor layout variation (and to let
 * tests place `agents/` at a shallow ancestor of the fixture skill root).
 */
function discoverWorkerTiers(skillRoot: string): Set<string> | null {
  let dir = skillRoot;
  for (let i = 0; i < 5; i++) {
    const agentsDir = join(dir, "agents");
    if (existsSync(agentsDir) && statSync(agentsDir).isDirectory()) {
      const tiers = new Set<string>();
      for (const f of readdirSync(agentsDir)) {
        if (f.startsWith(WORKER_PREFIX) && f.endsWith(".md")) {
          tiers.add(f.slice(WORKER_PREFIX.length, -".md".length));
        }
      }
      return tiers;
    }
    const parent = dirname(dir);
    if (parent === dir) break; // reached filesystem root
    dir = parent;
  }
  return null; // no agents/ dir found — worker-exists stays UNVERIFIED
}

/** Bind a skill root into the typed model (exported so tests can reuse it). */
export function bindSkill(skillRoot: string): BoundSkill {
  const referencesRoot = join(skillRoot, "references");
  const phasesDir = join(referencesRoot, "phases");
  const rel = (abs: string) => abs.replace(skillRoot + "/", "");
  const availableWorkerTiers = discoverWorkerTiers(skillRoot);

  const phases: BoundSkill["phases"] = [];
  const fragments: BoundSkill["fragments"] = new Map();
  const assemblers: BoundSkill["assemblers"] = new Map();

  if (!existsSync(phasesDir)) {
    return { referencesRoot, phases, fragments, assemblers, rel, availableWorkerTiers };
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

  return { referencesRoot, phases, fragments, assemblers, rel, availableWorkerTiers };
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
