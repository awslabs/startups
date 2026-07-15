// sync-vendored-shared.ts — keep each skill's `references/vendored/` tree byte-identical
// to the plugin-neutral canonical source under `skills/shared/`.
//
// WHY: the plugin-shared files (the DSL INTERPRETER contract, the estimate schemas,
// the pricing/tier data) are RUNTIME dependencies of a skill — INTERPRETER.md IS the
// program the LLM interprets. A skill that references them via a `../shared/` climb is
// NOT self-contained: lift the skill folder out (zip / copy / use standalone) and the
// climb dangles. So each skill VENDORS a copy under `references/vendored/`, and this
// script is the sync contract that keeps the copies honest (DRY preserved by the check,
// not by a single physical file — the lockfile pattern).
//
// Usage:
//   node sync-vendored-shared.ts           # CHECK mode: exit 1 if any copy drifts
//   node sync-vendored-shared.ts --write    # SYNC mode: copy canonical -> every vendored/
//
// Zero-dep: runs under Node 24 native TS type-stripping (same as the validator).

import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";

// Repo-root-relative locations. The script is invoked from the repo root (mise task).
const PLUGIN = "migrate/plugins/migration-to-aws";
const CANONICAL = join(PLUGIN, "skills/shared");
const SKILLS_DIR = join(PLUGIN, "skills");
const VENDORED_SUBPATH = "references/vendored"; // relative to each skill root

const write = process.argv.includes("--write");

/** Recursively list files under a dir (relative to it), or [] when absent. */
function walk(root: string, rel = ""): string[] {
  const abs = join(root, rel);
  if (!existsSync(abs)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(abs)) {
    const r = rel ? join(rel, entry) : entry;
    if (statSync(join(root, r)).isDirectory()) out.push(...walk(root, r));
    else out.push(r);
  }
  return out;
}

/** Discover skills that vendor shared files (have a references/vendored/ dir). */
function vendoringSkills(): string[] {
  if (!existsSync(SKILLS_DIR)) return [];
  return readdirSync(SKILLS_DIR)
    .filter((d) => statSync(join(SKILLS_DIR, d)).isDirectory() && d !== "shared")
    .filter((d) => existsSync(join(SKILLS_DIR, d, VENDORED_SUBPATH)));
}

const problems: string[] = [];
let synced = 0;

for (const skill of vendoringSkills()) {
  const vendoredRoot = join(SKILLS_DIR, skill, VENDORED_SUBPATH);

  // (1) every vendored file must exist in canonical and match it byte-for-byte.
  for (const rel of walk(vendoredRoot)) {
    if (rel === "README.md") continue; // the per-skill DO-NOT-EDIT marker is skill-owned
    const canonicalFile = join(CANONICAL, rel);
    const vendoredFile = join(vendoredRoot, rel);
    if (!existsSync(canonicalFile)) {
      problems.push(
        `${vendoredFile}: vendored file has no canonical source at ${canonicalFile} ` +
          `(a vendored copy must mirror skills/shared/ — delete it or add the source)`,
      );
      continue;
    }
    const a = readFileSync(canonicalFile);
    const b = readFileSync(vendoredFile);
    if (!a.equals(b)) {
      if (write) {
        copyFileSync(canonicalFile, vendoredFile);
        synced++;
      } else {
        problems.push(
          `${vendoredFile}: differs from canonical ${canonicalFile}. ` +
            `If you edited the CANONICAL source, run 'mise run shared:sync' to update this copy. ` +
            `If you edited THIS vendored copy by mistake, move your change to the canonical ` +
            `file FIRST — 'shared:sync' OVERWRITES vendored copies from canonical and will ` +
            `discard edits made here.`,
        );
      }
    }
  }
}

if (write) {
  console.log(`vendored-shared sync: OK (${synced} file(s) updated)`);
  process.exit(0);
}

if (problems.length) {
  console.error(`vendored-shared check: ${problems.length} problem(s)`);
  for (const p of problems) console.error(`  - ${p}`);
  process.exit(1);
}

const n = vendoringSkills().length;
console.log(`vendored-shared check: OK (${n} skill(s) with a references/vendored/ tree checked)`);
