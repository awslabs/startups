// cross-plugin-drift.ts — fail loudly when the two plugin copies of a shared
// skill tree drift apart.
//
// WHY: the migration skills live in TWO plugins — the canonical source under
// `migrate/plugins/migration-to-aws/skills/` and a consolidated copy under
// `advisor/plugins/aws-startup-advisor/skills/`. Because the copy lives at a
// DIFFERENT path, git can never raise a merge conflict between them: a fix that
// lands on one side is invisible to the other, and both `merge-base` and the
// per-plugin gates (shared:check, fixtures, frontmatter) stay green while the
// copies silently diverge. That is exactly how a set of merged upstream fixes
// got reverted by a stale copy. This check compares the two trees directly.
//
// HOW: for every file in the source skill trees, the advisor copy must exist and
// be byte-identical AFTER normalizing the known, intentional differences:
//   - the plugin-scoped invocation prefix  (migration-to-aws: <-> aws-startup-advisor:)
//   - hardcoded repo paths                 (migrate/plugins/... <-> advisor/plugins/...)
//   - the JSON Schema $id namespace form    (github.io URL <-> urn:)
// A small ALLOWLIST covers files that legitimately diverge in prose (the
// advisor copies name the sibling skills explicitly, or carry an added $comment).
// Any file NOT on the allowlist that still differs after normalization — or is
// missing from advisor — is drift and fails the build.
//
// Usage:  node cross-plugin-drift.ts            # exit 1 on unexpected drift
//         node cross-plugin-drift.ts --list     # print per-file status, exit 0
//
// Zero-dep: runs under Node 24 native TS type-stripping (same as the other tools).

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const SRC = "migrate/plugins/migration-to-aws";
const DST = "advisor/plugins/aws-startup-advisor";
const SKILLS = ["agent-advisor", "gcp-to-aws", "heroku-to-aws", "llm-to-bedrock", "tf-best-practices", "shared"];
const listMode = process.argv.includes("--list");

// Files that legitimately differ after normalization — the advisor copies carry
// deliberate semantic edits (platform-generic handoff phrasing that names the
// sibling skills, an added schema $comment). Paths are relative to a skill root,
// keyed by skill name. Keep this list tight: every entry is a spot the two trees
// are ALLOWED to disagree, so each is a place a future upstream fix could be
// silently missed — prefer normalization rules over allowlist entries where possible.
const ALLOWLIST: Record<string, Set<string>> = {
  "agent-advisor": new Set([
    "SKILL.md",
    "references/decision-refs/batch.md",
    "references/decision-refs/ecs.md",
    "references/decision-refs/eks.md",
    "references/decision-refs/lambda.md",
    "references/decision-refs/freshness.md",
    "references/decision-refs/model-selection.md",
    "references/handoff/handoff-migration.md",
    "references/output-templates/recommendation-doc.md",
    "references/phases/clarify/clarify.md",
    "references/phases/design/design.md",
    "references/phases/discover/discover.md",
    "references/phases/estimate/estimate.md",
    "references/phases/migration-plan/migration-plan.md",
    "references/vendored/dsl/INTERPRETER.md",
    "scripts/build_diagram.py",
    "scripts/test_build_diagram.py",
    "scripts/test_unit_grouping.py",
  ]),
  "heroku-to-aws": new Set([
    "references/vendored/dsl/INTERPRETER.md",
    "references/vendored/estimate/estimation-infra.schema.json",
    "references/vendored/state/phase-status.schema.json",
  ]),
  "llm-to-bedrock": new Set([
    "SKILL.md",
  ]),
  "shared": new Set([
    "dsl/INTERPRETER.md",
    "estimate/estimation-infra.schema.json",
    "state/phase-status.schema.json",
  ]),
};

/** Normalize the known, intentional token differences so only real drift shows. */
function normalize(s: string): string {
  return s
    .replaceAll("aws-startup-advisor:", "migration-to-aws:")
    .replaceAll("advisor/plugins/aws-startup-advisor", "migrate/plugins/migration-to-aws")
    .replaceAll(
      "urn:awslabs:startups:migration-to-aws:state:phase-status",
      "https://awslabs.github.io/startups/migration-to-aws/state/phase-status.schema.json",
    )
    .replaceAll(
      "urn:awslabs:startups:migration-to-aws:estimate:estimation-infra",
      "https://awslabs.github.io/startups/migration-to-aws/estimate/estimation-infra.schema.json",
    );
}

/** Recursively list files under a dir (relative to it), skipping python caches. */
function walk(root: string, rel = ""): string[] {
  const abs = join(root, rel);
  if (!existsSync(abs)) return [];
  const out: string[] = [];
  for (const entry of readdirSync(abs)) {
    if (entry === "__pycache__" || entry === ".pytest_cache" || entry === ".venv" || entry.endsWith(".pyc")) continue;
    const r = rel ? join(rel, entry) : entry;
    if (statSync(join(root, r)).isDirectory()) out.push(...walk(root, r));
    else out.push(r);
  }
  return out;
}

const drift: string[] = [];
const missing: string[] = [];
let allowlisted = 0;
let identical = 0;

for (const skill of SKILLS) {
  const srcRoot = join(SRC, "skills", skill);
  const dstRoot = join(DST, "skills", skill);
  const allow = ALLOWLIST[skill] ?? new Set<string>();
  for (const rel of walk(srcRoot)) {
    const df = join(dstRoot, rel);
    if (!existsSync(df)) {
      missing.push(`skills/${skill}/${rel}`);
      continue;
    }
    const same = normalize(readFileSync(join(srcRoot, rel), "utf8")) === normalize(readFileSync(df, "utf8"));
    if (same) {
      identical++;
    } else if (allow.has(rel)) {
      allowlisted++;
      if (listMode) console.log(`allow  skills/${skill}/${rel}`);
    } else {
      drift.push(`skills/${skill}/${rel}`);
    }
  }
}

if (listMode) {
  console.log(`\n${identical} identical, ${allowlisted} allowlisted, ${drift.length} drift, ${missing.length} missing`);
  process.exit(0);
}

if (missing.length || drift.length) {
  if (missing.length) {
    console.error(`cross-plugin drift: ${missing.length} file(s) present in ${SRC} but MISSING from ${DST}:`);
    for (const m of missing) console.error(`  - ${m}`);
  }
  if (drift.length) {
    console.error(
      `cross-plugin drift: ${drift.length} file(s) differ after normalization and are not allowlisted `
        + `(a fix likely landed on the ${SRC} side only — re-copy + re-apply prefix rewrites, or add to ALLOWLIST if intentional):`,
    );
    for (const d of drift) console.error(`  - ${d}`);
  }
  process.exit(1);
}

console.log(`cross-plugin drift check: OK (${identical} identical, ${allowlisted} allowlisted across ${SKILLS.length} skill trees)`);
