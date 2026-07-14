// types.ts — the minimal typed model of the heroku-to-aws phase frontmatter.
//
// This is the shape the parser binds raw frontmatter into, and what the checks
// operate on. Kept intentionally small: only the keys the frontmatter uses today
// (phase composition + fragment/assembler units). Mirrors INTERPRETER.md.

/** A fragment's run condition (see INTERPRETER.md § _trigger forms). */
export type Trigger =
  | { kind: "always" }
  | { kind: "glob"; pattern: string }
  | { kind: "when"; condition: string } // opaque prose condition; bound but NOT evaluated by CI (the LLM evaluates it at runtime)
  | { kind: "unknown"; raw: string }; // parsed but not a recognized form → a check flags it

/** One entry in a phase's `_fragments` list. */
export interface FragmentRef {
  id: string;
  trigger: Trigger;
  file: string; // path relative to the skill's references/ root
}

/** A phase's stale-downstream re-entry guard (see INTERPRETER.md § _re_entry_guard). */
export interface ReEntryGuard {
  staleIfCompleted: string | null; // _stale_if_completed — downstream phase whose completion blocks re-run
  staleArtifact: string | null; // _stale_artifact — the artifact named in the GATE_FAIL field
  onReentry: string | null; // _on_reentry — closed enum
  onConfirm: string | null; // _on_confirm — closed enum
  unknownKeys: string[]; // sub-keys not in the closed guard vocab
}

/** One check in a `_preconditions` / `_postconditions` list. */
export interface CheckItem {
  kind: string; // the check keyword: _check_phase_completed | _check_single_active_phase | _check_file_exists | _validate_json | _assert (or an unknown keyword → flagged)
  arg: string[]; // normalized args (phase name / filenames / [] for _assert / the assert prose)
  onFailure: string | null; // _on_failure action name
}

/**
 * A phase's `_exec` block — its EXECUTION MODE (see INTERPRETER.md § `_exec`).
 * When present, the phase's WORK (its fragments + assembler) runs in a fresh,
 * isolated sub-agent window with file-only I/O; the interpreter keeps the phase's
 * entry gate, completion gate, `_init` state setup, and the state transition
 * (`HANDOFF_OK` + `.phase-status.json` write) in the MAIN window. Absent = the
 * phase runs inline in the main window, as today.
 */
export interface ExecSpec {
  agent: string | null; // _agent — the capability tier the phase's work runs at (closed enum: ro | rw | git)
  unknownKeys: string[]; // sub-keys not in the closed _exec vocab
}

/** One entry in a phase's `_knowledge` list (a JSON data dependency). */
export interface KnowledgeRef {
  file: string; // path relative to the skill root
  when: string | null; // optional opaque prose condition (bound, not evaluated by CI)
}

/**
 * One entry in a `_produces` / `_contributes` list. An artifact is either
 * unconditional (a bare filename, `when: null`) or CONDITIONAL (an inline
 * `{ file: <path>, _when: <prose> }` map — produced only when the design predicate
 * holds). Mirrors `_knowledge`'s `{ file, _when }` shape. `when` is opaque prose,
 * bound but NOT evaluated by CI (same as `_knowledge._when`). A trailing-slash
 * `file` (e.g. `kubernetes/`) denotes a produced DIRECTORY, used when a unit emits
 * a set of dynamically-named files with no single fixed filename.
 */
export interface ArtifactRef {
  file: string;
  when: string | null;
}

/** The phase orchestrator file's frontmatter. */
export interface PhaseFrontmatter {
  kind: "phase";
  sourceFile: string; // absolute path, for messages
  phase: string; // _phase
  title: string | null;
  /** _kind: 'checkpoint' (off-backbone, trigger-entered) or 'backbone' (default when absent). */
  role: "backbone" | "checkpoint";
  requiresPhase: string | null;
  init: boolean; // _init
  /** _interactive: does this phase's WORK (fragments + assembler) prompt the user?
   *  A phase MAY only be dispatched via `_exec` when this is explicitly `false`
   *  (a file-only worker cannot converse). null = the key is absent (unspecified). */
  interactive: boolean | null;
  fragments: FragmentRef[];
  /** phase-level _trigger (checkpoint phases only) — how the phase is entered. null for backbone. */
  trigger: Trigger | null;
  assembleFile: string | null; // _assemble._file
  produces: string[]; // _produces filenames (bare + conditional, filename only)
  producesRefs: ArtifactRef[]; // _produces with conditional metadata ({file, when})
  advancesTo: string | null;
  exec: ExecSpec | null; // _exec execution mode (agent dispatch); null when the phase runs inline
  reEntryGuard: ReEntryGuard | null; // _re_entry_guard (backbone phases with a downstream); null when absent
  preconditions: CheckItem[]; // _preconditions (entry gate); empty when absent
  postconditions: CheckItem[]; // _postconditions (completion gate); empty when absent
  forbidsFiles: string[]; // _forbids_files globs; empty when absent
  input: string[]; // _input entries (artifacts / 'workspace' / a glob)
  knowledge: KnowledgeRef[]; // _knowledge JSON data deps; empty when absent
  unknownKeys: string[]; // top-level _keys not in the closed vocab
}

/** A fragment unit file's frontmatter. */
export interface FragmentFrontmatter {
  kind: "fragment";
  sourceFile: string;
  fragment: string; // _fragment (id)
  ofPhase: string | null; // _of_phase
  contributes: string[]; // _contributes filenames (bare + conditional, filename only)
  contributesRefs: ArtifactRef[]; // _contributes with conditional metadata ({file, when})
  unknownKeys: string[];
}

/** The assembler unit file's frontmatter. */
export interface AssemblerFrontmatter {
  kind: "assembler";
  sourceFile: string;
  assemble: string | null; // _assemble (id)
  ofPhase: string | null;
  reads: string[];
  produces: string[]; // _produces filenames (bare + conditional, filename only)
  producesRefs: ArtifactRef[]; // _produces with conditional metadata ({file, when})
  knowledge: KnowledgeRef[]; // _knowledge reference/data deps; empty when absent
  unknownKeys: string[];
}

/** A validation problem. */
export interface Finding {
  file: string; // path relative to skill root, for readable output
  message: string;
}
