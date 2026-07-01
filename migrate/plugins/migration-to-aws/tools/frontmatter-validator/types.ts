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

/** The phase orchestrator file's frontmatter. */
export interface PhaseFrontmatter {
  kind: "phase";
  sourceFile: string; // absolute path, for messages
  phase: string; // _phase
  title: string | null;
  requiresPhase: string | null;
  init: boolean; // _init
  fragments: FragmentRef[];
  assembleFile: string | null; // _assemble._file
  produces: string[];
  advancesTo: string | null;
  unknownKeys: string[]; // top-level _keys not in the closed vocab
}

/** A fragment unit file's frontmatter. */
export interface FragmentFrontmatter {
  kind: "fragment";
  sourceFile: string;
  fragment: string; // _fragment (id)
  ofPhase: string | null; // _of_phase
  contributes: string[];
  unknownKeys: string[];
}

/** The assembler unit file's frontmatter. */
export interface AssemblerFrontmatter {
  kind: "assembler";
  sourceFile: string;
  assemble: string | null; // _assemble (id)
  ofPhase: string | null;
  reads: string[];
  produces: string[];
  unknownKeys: string[];
}

/** A validation problem. */
export interface Finding {
  file: string; // path relative to skill root, for readable output
  message: string;
}
