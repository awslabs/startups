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
import { CHECK_KINDS, ON_ERROR_ACTIONS } from "./parse.ts";

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

    // backbone/checkpoint contract (see INTERPRETER.md § _kind):
    //   backbone (default): MUST have _advances_to; MUST NOT have a phase-level _trigger.
    //   checkpoint: MUST have a phase-level _trigger; MUST NOT have _advances_to
    //               (off-backbone — entered by its trigger, returns control).
    if (phase.role === "checkpoint") {
      if (!phase.trigger) {
        add(pf, `checkpoint phase '${phase.phase}' must declare a phase-level _trigger (how it is entered)`);
      } else if (phase.trigger.kind === "unknown") {
        add(pf, `checkpoint phase '${phase.phase}' has an unrecognized phase _trigger form: ${phase.trigger.raw}`);
      }
      if (phase.advancesTo) {
        add(pf, `checkpoint phase '${phase.phase}' must NOT declare _advances_to (it is off-backbone; it returns control, it does not advance)`);
      }
    } else {
      // backbone
      if (!phase.advancesTo) {
        add(pf, `backbone phase '${phase.phase}' must declare _advances_to (or mark it '_kind: checkpoint' if it is an off-backbone checkpoint)`);
      }
      if (phase.trigger) {
        add(pf, `backbone phase '${phase.phase}' must NOT declare a phase-level _trigger (only checkpoint phases are trigger-entered)`);
      }
    }

    // _requires_phase membership: verify only when >1 phase declares frontmatter AND
    // the target is not itself declared (otherwise UNVERIFIED — tolerant of partial rollout).
    if (phase.requiresPhase && declaredPhases.size > 1 && !declaredPhases.has(phase.requiresPhase)) {
      add(pf, `_requires_phase '${phase.requiresPhase}' names no declared phase`);
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
    // single-creator (creates-vs-contributes model, INTERPRETER § assembler): each
    // phase _produces artifact must have exactly ONE creator.
    //   - If the assembler _produces it → the assembler is the creator; fragments that
    //     also name it in _contributes are CONTENT-contributors (allowed, no conflict).
    //   - Otherwise exactly one fragment must _contributes it (that fragment is the
    //     creator). Zero → uncreated; two+ fragments → ambiguous creator.
    const fragCreators = new Map<string, string[]>(); // artifact -> fragment ids declaring it
    for (const fr of phase.fragments) {
      const frag = skill.fragments.get(join(skill.referencesRoot, fr.file));
      if (frag) for (const art of frag.contributes) {
        (fragCreators.get(art) ?? fragCreators.set(art, []).get(art)!).push(fr.id);
      }
    }
    for (const art of phase.produces) {
      if (asm.produces.includes(art)) continue; // assembler is the creator; fragments contribute
      const fcs = fragCreators.get(art) ?? [];
      if (fcs.length === 0) {
        add(pf, `phase _produces '${art}' but no unit creates it (not in the assembler _produces, and no fragment _contributes it) — single-creator rule`);
      } else if (fcs.length > 1) {
        add(pf, `phase _produces '${art}' is declared by multiple fragments (${fcs.join(", ")}) with no assembler owner — ambiguous creator (single-creator rule)`);
      }
    }
  }

  // ---- Re-entry guard checks (INTERPRETER.md § _re_entry_guard) ----
  // The guard is skill-agnostic structure: a phase's re-run is stale-blocked by the
  // completion of the phase it advances to. Enforced per-phase; cross-phase artifact
  // check runs once the downstream phase's frontmatter is present.
  const guardOnReentry = new Set(["stop_unless_confirmed"]);
  const guardOnConfirm = new Set(["reset_downstream_to_pending"]);
  const phasesByName = new Map(skill.phases.map((p) => [p.phase, p] as const));
  for (const phase of skill.phases) {
    const g = phase.reEntryGuard;
    if (!g) continue;
    const pf = skill.rel(phase.sourceFile);

    // unknown sub-keys (typo catch)
    for (const k of g.unknownKeys) add(pf, `unknown _re_entry_guard sub-key '${k}'`);

    // required-together: all four sub-keys present
    if (!g.staleIfCompleted) add(pf, `_re_entry_guard missing _stale_if_completed`);
    if (!g.staleArtifact) add(pf, `_re_entry_guard missing _stale_artifact`);
    if (!g.onReentry) add(pf, `_re_entry_guard missing _on_reentry`);
    if (!g.onConfirm) add(pf, `_re_entry_guard missing _on_confirm`);

    // enum membership
    if (g.onReentry && !guardOnReentry.has(g.onReentry)) {
      add(pf, `_re_entry_guard._on_reentry '${g.onReentry}' is not a recognized value (expected: stop_unless_confirmed)`);
    }
    if (g.onConfirm && !guardOnConfirm.has(g.onConfirm)) {
      add(pf, `_re_entry_guard._on_confirm '${g.onConfirm}' is not a recognized value (expected: reset_downstream_to_pending)`);
    }

    // a terminal-advancing phase (or one with no downstream) must NOT carry a guard
    if (!phase.advancesTo || TERMINALS.has(phase.advancesTo)) {
      add(pf, `phase '${phase.phase}' has a _re_entry_guard but no downstream backbone phase (its _advances_to is '${phase.advancesTo ?? "(none)"}') — a guard is meaningless with nothing downstream`);
    }

    // guard ⟺ advancer: the phase is stale-blocked by the completion of the phase
    // it advances to. _stale_if_completed SHOULD equal _advances_to.
    if (g.staleIfCompleted && phase.advancesTo && !TERMINALS.has(phase.advancesTo) &&
        g.staleIfCompleted !== phase.advancesTo) {
      add(pf, `_re_entry_guard._stale_if_completed '${g.staleIfCompleted}' should equal this phase's _advances_to '${phase.advancesTo}' (a phase's re-run is stale-blocked by the completion of the phase it advances to)`);
    }

    // phase-ref resolves: _stale_if_completed names a declared phase (verify only when
    // that phase has frontmatter — tolerant of partial rollout).
    if (g.staleIfCompleted && declaredPhases.size > 1 && !declaredPhases.has(g.staleIfCompleted)) {
      add(pf, `_re_entry_guard._stale_if_completed '${g.staleIfCompleted}' names no declared phase`);
    }

    // artifact ⟺ downstream _produces (HARD FAIL): _stale_artifact must be one of the
    // downstream phase's _produces. Checked only when the downstream phase's
    // frontmatter is present (otherwise UNVERIFIED — partial rollout).
    if (g.staleIfCompleted && g.staleArtifact) {
      const downstream = phasesByName.get(g.staleIfCompleted);
      if (downstream && !downstream.produces.includes(g.staleArtifact)) {
        add(pf, `_re_entry_guard._stale_artifact '${g.staleArtifact}' is not in the _produces of the downstream phase '${g.staleIfCompleted}' (declared: ${downstream.produces.join(", ") || "(none)"})`);
      }
    }
  }

  // ---- Gate checks: _preconditions / _postconditions / _forbids_files ----
  // (INTERPRETER.md § Gate protocol.) Structural only: closed check-kind vocab,
  // _on_failure action membership, phase-ref resolution, and the postcondition⟺
  // _produces cross-check. _assert bodies are opaque prose (bound, not evaluated).
  for (const phase of skill.phases) {
    const pf = skill.rel(phase.sourceFile);
    const checkList = (items: typeof phase.preconditions, label: string) => {
      for (const c of items) {
        if (!CHECK_KINDS.has(c.kind)) {
          add(pf, `unknown ${label} check kind '${c.kind}' (allowed: ${[...CHECK_KINDS].join(", ")})`);
        }
        if (c.onFailure && !ON_ERROR_ACTIONS.has(c.onFailure)) {
          add(pf, `${label} check '${c.kind}' has an unrecognized _on_failure action '${c.onFailure}' (allowed: ${[...ON_ERROR_ACTIONS].join(", ")})`);
        }
        // _check_phase_completed arg SHOULD name a declared phase (partial-rollout tolerant).
        if (c.kind === "_check_phase_completed" && c.arg[0] && declaredPhases.size > 1 && !declaredPhases.has(c.arg[0])) {
          add(pf, `${label} _check_phase_completed '${c.arg[0]}' names no declared phase`);
        }
      }
    };
    checkList(phase.preconditions, "_preconditions");
    checkList(phase.postconditions, "_postconditions");

    // postcondition file-exists ⟺ _produces (HARD FAIL): a phase can only assert the
    // existence of a file it declares it produces — forces _produces to be the real
    // artifact set (guards against a hollow _produces).
    for (const c of phase.postconditions) {
      if (c.kind === "_check_file_exists") {
        for (const f of c.arg) {
          if (!phase.produces.includes(f)) {
            add(pf, `_postconditions asserts _check_file_exists '${f}' but it is not in this phase's _produces (declared: ${phase.produces.join(", ") || "(none)"}) — a phase may only gate on artifacts it declares it produces`);
          }
        }
      }
    }
  }

  // ---- Backbone chain-consistency (backbone phases only; checkpoints excluded) ----
  // The backbone is the linear lifecycle wired by _advances_to (forward) and
  // _requires_phase (backward). Checkpoints (_kind: checkpoint) are off-backbone and
  // are NOT part of this graph. Enforced only once >1 phase declares frontmatter AND
  // every backbone _advances_to target is either a terminal or a declared phase
  // (i.e. the backbone is fully present — tolerant of partial rollout).
  const backbone = skill.phases.filter((p) => p.role === "backbone");
  if (backbone.length > 1) {
    const byName = new Map(backbone.map((p) => [p.phase, p] as const));
    const advTargetsResolvable = backbone.every(
      (p) => !p.advancesTo || TERMINALS.has(p.advancesTo) || byName.has(p.advancesTo),
    );
    if (advTargetsResolvable) {
      const relOf = (p: PhaseFrontmatter) => skill.rel(p.sourceFile);

      // (1) single head: exactly one backbone phase with no _requires_phase.
      const heads = backbone.filter((p) => !p.requiresPhase);
      if (heads.length !== 1) {
        const names = heads.map((h) => h.phase).join(", ") || "(none)";
        add(relOf(backbone[0]), `backbone must have exactly one head (a phase with no _requires_phase); found ${heads.length}: ${names}`);
      }

      // (2) single terminal: exactly one backbone phase advancing to a terminal.
      const terminals = backbone.filter((p) => p.advancesTo && TERMINALS.has(p.advancesTo));
      if (terminals.length !== 1) {
        const names = terminals.map((t) => t.phase).join(", ") || "(none)";
        add(relOf(backbone[0]), `backbone must have exactly one terminal (a phase whose _advances_to is complete/done/end); found ${terminals.length}: ${names}`);
      }

      // (3) forward⇒back: if A _advances_to B and B is a backbone phase, B must _requires_phase A.
      for (const a of backbone) {
        if (a.advancesTo && !TERMINALS.has(a.advancesTo)) {
          const b = byName.get(a.advancesTo);
          if (b && b.requiresPhase !== a.phase) {
            add(relOf(a), `chain inconsistency: '${a.phase}' _advances_to '${b.phase}', but '${b.phase}' _requires_phase '${b.requiresPhase ?? "(none)"}' (expected '${a.phase}')`);
          }
        }
      }

      // (4) back⇒forward: if B _requires_phase A (both backbone), A must _advances_to B.
      for (const b of backbone) {
        if (b.requiresPhase && byName.has(b.requiresPhase)) {
          const a = byName.get(b.requiresPhase)!;
          if (a.advancesTo !== b.phase) {
            add(relOf(b), `chain inconsistency: '${b.phase}' _requires_phase '${a.phase}', but '${a.phase}' _advances_to '${a.advancesTo ?? "(none)"}' (expected '${b.phase}')`);
          }
        }
      }
    }
  }

  // ---- _knowledge (JSON data deps resolve) + _input (resolves to an upstream _produces) ----
  const skillRoot = join(skill.referencesRoot, "..");
  // every artifact any declared phase produces (for _input resolution)
  const allProduced = new Set<string>();
  for (const p of skill.phases) for (const art of p.produces) allProduced.add(art);
  const INPUT_LITERALS = new Set(["workspace"]);
  const isGlob = (s: string) => /[*?{]/.test(s);

  // assembler _knowledge files must resolve on disk too (relative to the skill root).
  for (const asm of skill.assemblers.values()) {
    for (const k of asm.knowledge) {
      if (!existsSync(join(skillRoot, k.file))) {
        add(skill.rel(asm.sourceFile), `_knowledge file does not resolve: ${k.file}`);
      }
    }
  }

  for (const phase of skill.phases) {
    const pf = skill.rel(phase.sourceFile);

    // _knowledge files must resolve on disk (relative to the skill root). _when opaque.
    for (const k of phase.knowledge) {
      if (!existsSync(join(skillRoot, k.file))) {
        add(pf, `_knowledge file does not resolve: ${k.file}`);
      }
    }

    // _input resolution: each entry is 'workspace', a glob (e.g. the phase-status file),
    // or an artifact produced by some declared phase. Enforce the produced-by check only
    // once >1 phase declares frontmatter (partial-rollout tolerant).
    for (const inp of phase.input) {
      if (INPUT_LITERALS.has(inp) || isGlob(inp)) continue;
      if (declaredPhases.size > 1 && !allProduced.has(inp)) {
        add(pf, `_input '${inp}' is not produced by any declared phase (no phase declares it in _produces)`);
      }
    }
  }

  return findings;
}
