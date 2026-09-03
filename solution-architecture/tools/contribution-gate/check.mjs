#!/usr/bin/env node
// Mechanical half of the solution-architecture contribution gate.
//
// Checks only what can be decided deterministically from file contents. The
// judgment criteria (is this genuinely startup-specific, does it overlap Agent
// Toolkit for AWS) are left to human and agent review, because a grep cannot
// settle them and pretending otherwise would produce false confidence.
//
// Usage:
//   node check.mjs <file>...      explicit file list (CI passes changed files)
//   node check.mjs                scan all SKILL.md under solution-architecture/
//
// Exit 0 = pass, 1 = violations found, 2 = harness error.

import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const REPO_ROOT = process.cwd();
const SCOPE_DIR = "solution-architecture";

// Services that are sunset, closed to new customers, or end-of-support.
// Mentioning one to warn against it or migrate off it is allowed, so each
// match is checked for a nearby warning cue before it is reported.
const SUNSET = [
  { pattern: /\bApp Mesh\b/gi, name: "AWS App Mesh" },
  { pattern: /\bApp Runner\b/gi, name: "AWS App Runner" },
  { pattern: /\bS3 Select\b/gi, name: "S3 Select" },
  { pattern: /\bGlacier Select\b/gi, name: "Glacier Select" },
  { pattern: /\bIoT Analytics\b/gi, name: "AWS IoT Analytics" },
  {
    pattern: /\bKinesis Data Analytics\b/gi,
    name:
      "Kinesis Data Analytics (renamed to Amazon Managed Service for Apache Flink in 2023; " +
      "the \"for SQL Applications\" variant was discontinued and its applications deleted from 2026-01-27)",
  },
  { pattern: /\bAurora Serverless v1\b/gi, name: "Aurora Serverless v1" },
  { pattern: /\blaunch configuration/gi, name: "EC2 launch configurations" },
  { pattern: /\bCloud9\b/gi, name: "AWS Cloud9" },
  { pattern: /\bSimpleDB\b/gi, name: "Amazon SimpleDB" },
  // AWS CodeCommit was here and has been removed. It closed to new customers on
  // 2024-07-25 and REOPENED on 2025-11-25, so recommending it is fine again and
  // flagging it was a false positive. See the CodeCommit user guide document history.
  //
  // Re-verify this list rather than trusting it. A closure is announced loudly and a
  // reopening is not, so an entry here rots silently in the direction that blocks
  // correct advice. This check is meant to stop bad recommendations, and a stale entry
  // makes it stop good ones. Last audited 2026-09-01.
];

// Frontmatter fields the official skill validator accepts. Notably `when_to_use`
// is deprecated and `version` is rejected, so both are flagged here rather than
// silently shipped.
const ALLOWED_FRONTMATTER = new Set([
  "name",
  "description",
  "license",
  "allowed-tools",
  "disallowed-tools",
  "metadata",
  "compatibility",
  "paths",
  "shell",
  "user-invocable",
  "model",
]);

const DESCRIPTION_MAX = 1024; // enforced by skill-creator/scripts/quick_validate.py

/**
 * Plugins a Skill("plugin:skill") pointer may target: the declared upstream
 * dependencies, plus sibling plugins in this repo.
 *
 * Skills inside this repo are verified to exist. Upstream skills cannot be,
 * because aws-core and aws-agents are external dependencies that are not
 * checked out in CI, so only the plugin prefix is validated for those. A typo
 * in an upstream skill name is caught by review rather than here, and claiming
 * otherwise would be a check that silently passes everything.
 */
function resolvableSkillTargets() {
  const inRepo = new Map(); // plugin name -> Set of skill names
  const pluginRoots = ["advisor/plugins", "migrate/plugins", "solution-architecture/plugins"];
  for (const root of pluginRoots) {
    if (!existsSync(root)) continue;
    for (const plugin of readdirSync(root)) {
      const skillsDir = join(root, plugin, "skills");
      if (!existsSync(skillsDir)) continue;
      const skills = new Set();
      for (const entry of readdirSync(skillsDir)) {
        if (existsSync(join(skillsDir, entry, "SKILL.md"))) skills.add(entry);
      }
      inRepo.set(plugin, skills);
    }
  }
  return inRepo;
}

/** Upstream plugin prefixes declared as dependencies in any plugin.json here. */
function declaredDependencyPlugins() {
  const deps = new Set();
  const root = "solution-architecture/plugins";
  if (!existsSync(root)) return deps;
  for (const plugin of readdirSync(root)) {
    const manifest = join(root, plugin, ".claude-plugin", "plugin.json");
    if (!existsSync(manifest)) continue;
    try {
      const json = JSON.parse(readFileSync(manifest, "utf8"));
      for (const d of json.dependencies ?? []) {
        deps.add(typeof d === "string" ? d : d.name);
      }
    } catch {
      /* manifest validity is claude plugin validate's job, not ours */
    }
  }
  return deps;
}

const findings = [];
const add = (file, criterion, line, message) =>
  findings.push({ file, criterion, line, message });

/**
 * Observations reported without failing the build.
 *
 * A note is something a reader should look at and a script cannot settle. The sunset
 * check is the only one here of that kind, because telling a recommendation from a
 * warning is a judgment about meaning, and three attempts to do it with cue words all
 * failed in both directions at once. Review recorded six phrasings that recommended a
 * sunset service and passed, because words like `legacy`, `retired`, and `deprecat`
 * exempted the whole line however they were used, and three more where a directional
 * phrase such as "instead of Jenkins, use App Runner" exempted the service being
 * recommended rather than the one being left.
 *
 * So the script now reports every mention and judges none of them. That has no false
 * negatives, since nothing is exempted, and no false positives that can block, since
 * notes do not fail. Deciding whether a mention recommends or warns belongs to the
 * advisory reviewer, which reads the surrounding prose and owns the `staleness` axis.
 */
const notes = [];
const note = (file, criterion, line, message) =>
  notes.push({ file, criterion, line, message });

/**
 * Collect every markdown file in scope.
 *
 * Sunset-service and style checks apply to ALL of them, because the historical
 * bug lived in reference files rather than in SKILL.md: the removed
 * aws-dev-toolkit recommended App Mesh in references/compute.md and App Runner
 * in references/cost-comparison.md. Checking only SKILL.md would leave the one
 * place these have actually appeared unguarded.
 */
function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else if (entry.endsWith(".md")) out.push(full);
  }
  return out;
}

const isSkill = (f) => f.endsWith("SKILL.md");

function lineOf(text, index) {
  return text.slice(0, index).split("\n").length;
}

/**
 * Criterion 3 and prose style. Applies to every markdown file in scope,
 * including reference files, assets, and plugin READMEs.
 */
function checkAnyMarkdown(file) {
  const text = readFileSync(file, "utf8");
  const rel = relative(REPO_ROOT, file);
  const lines = text.split("\n");

  // --- sunset services ----------------------------------------------------
  for (const { pattern, name } of SUNSET) {
    pattern.lastIndex = 0;
    let m;
    while ((m = pattern.exec(text)) !== null) {
      const lineNo = lineOf(text, m.index);
      note(
        rel,
        "sunset-service",
        lineNo,
        `Mentions ${name}. Warning against it is fine; recommending it is not. ` +
          `This script only reports the mention, it does not judge the framing.`,
      );
    }
  }

  // --- em/en dashes -------------------------------------------------------
  const dash = text.match(/[—–]/);
  if (dash) {
    add(
      rel,
      "style",
      lineOf(text, dash.index),
      "Contains an em dash or en dash. This folder uses commas, periods, parentheses, or plain hyphens.",
    );
  }
}

/**
 * Skill-manifest checks. SKILL.md only, since it is the only file Claude Code
 * discovers and the only one whose frontmatter is load-bearing. Reference files
 * are pulled in on demand by a link from SKILL.md and carry no frontmatter
 * contract, so requiring `audience:` on them would be wrong.
 */
function checkSkillManifest(file) {
  const text = readFileSync(file, "utf8");
  const rel = relative(REPO_ROOT, file);

  const fm = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!fm) {
    add(rel, "frontmatter", 1, "No YAML frontmatter block found.");
  } else {
    const front = fm[1];
    if (!/^\s*audience:\s*startup\s*$/m.test(front)) {
      add(
        rel,
        "audience",
        1,
        "Missing `audience: startup` under `metadata:` in frontmatter. Required by solution-architecture/CONTRIBUTING.md.",
      );
    }
    if (!/^\s*name:\s*\S+/m.test(front)) {
      add(rel, "frontmatter", 1, "Frontmatter is missing a `name:` field.");
    }
    if (!/^\s*description:\s*\S/m.test(front)) {
      add(rel, "frontmatter", 1, "Frontmatter is missing a `description:` field.");
    }

    // Top-level keys only, so `audience:` nested under `metadata:` is not
    // mistaken for an unknown field.
    for (const m of front.matchAll(/^([A-Za-z][\w-]*):/gm)) {
      const key = m[1];
      if (ALLOWED_FRONTMATTER.has(key)) continue;
      const hint = key === "when_to_use"
        ? "`when_to_use` is deprecated; put triggering information in `description`."
        : key === "version"
        ? "`version` is rejected by the official skill validator; remove it."
        : `Unknown frontmatter field \`${key}\`.`;
      add(rel, "frontmatter", 1 + lineOf(front, m.index), hint);
    }

    // Hard limit enforced by the official validator; over it, text is truncated.
    const desc = front.match(/^description:\s*(?:"([\s\S]*?)"|'([\s\S]*?)'|(.+))\s*$/m);
    if (desc) {
      const value = (desc[1] ?? desc[2] ?? desc[3] ?? "").trim();
      if (value.length > DESCRIPTION_MAX) {
        add(
          rel,
          "description-length",
          1,
          `description is ${value.length} characters, over the ${DESCRIPTION_MAX} limit enforced by the official skill validator. Text past the limit is truncated.`,
        );
      }
    }
  }

  // --- invocable upstream pointers ----------------------------------------
  // A plugin whose premise is deference is worthless if its pointers are wrong.
  const inRepo = resolvableSkillTargets();
  const upstream = declaredDependencyPlugins();
  for (const m of text.matchAll(/Skill\(\s*"([^"]+)"\s*\)/g)) {
    const target = m[1];
    if (!target.includes(":")) continue; // bare skill name, not a plugin pointer
    const [plugin, skill] = target.split(":");
    const lineNo = lineOf(text, m.index);

    if (inRepo.has(plugin)) {
      if (!inRepo.get(plugin).has(skill)) {
        add(
          rel,
          "broken-pointer",
          lineNo,
          `Skill("${target}") names no skill that exists in this repo. Plugin \`${plugin}\` has no \`${skill}\` skill.`,
        );
      }
    } else if (!upstream.has(plugin)) {
      add(
        rel,
        "broken-pointer",
        lineNo,
        `Skill("${target}") points at plugin \`${plugin}\`, which is neither in this repo nor a declared dependency in plugin.json.`,
      );
    }
  }

  // "toolkit" is banned in names. Prose references to the upstream product
  // "Agent Toolkit for AWS" are expected and allowed.
  const nameMatch = text.match(/^\s*name:\s*(.+)$/m);
  if (nameMatch && /toolkit/i.test(nameMatch[1])) {
    add(
      rel,
      "naming",
      lineOf(text, nameMatch.index),
      `Skill name must not contain "toolkit": ${nameMatch[1].trim()}`,
    );
  }

  // A reference file nothing links to is never loaded by Claude Code, so it is
  // dead weight rather than content. Flag orphans at authoring time.
  const skillDir = file.slice(0, file.lastIndexOf("/"));
  const refDir = join(skillDir, "references");
  if (existsSync(refDir)) {
    for (const entry of readdirSync(refDir)) {
      if (!entry.endsWith(".md")) continue;
      if (!text.includes(`references/${entry}`)) {
        add(
          rel,
          "orphan-reference",
          1,
          `references/${entry} is not linked from this SKILL.md, so Claude Code will never load it. Link it or remove it.`,
        );
      }
    }
  }
}

function main() {
  const args = process.argv.slice(2);
  let files;

  if (args.length > 0) {
    files = args
      .filter((f) => f.endsWith(".md"))
      .filter((f) => f.startsWith(SCOPE_DIR))
      .filter((f) => existsSync(f)); // skip deletions
  } else {
    files = existsSync(SCOPE_DIR) ? walk(SCOPE_DIR) : [];
  }

  if (files.length === 0) {
    console.log("contribution-gate: no in-scope markdown files to check.");
    return 0;
  }

  for (const f of files) {
    checkAnyMarkdown(f);
    if (isSkill(f)) checkSkillManifest(f);
  }

  const skillCount = files.filter(isSkill).length;
  console.log(
    `contribution-gate: checked ${files.length} markdown file(s), ` +
      `${skillCount} of them SKILL.md.\n`,
  );

  /** Group by file, newest-shallowest first, for a readable report. */
  const report = (items) => {
    const byFile = new Map();
    for (const f of items) {
      if (!byFile.has(f.file)) byFile.set(f.file, []);
      byFile.get(f.file).push(f);
    }
    for (const [file, fs] of [...byFile].sort(([a], [b]) => a.localeCompare(b))) {
      console.log(`${file}`);
      for (const f of fs.sort((a, b) => a.line - b.line)) {
        console.log(`  L${f.line}  [${f.criterion}] ${f.message}`);
      }
      console.log("");
    }
  };

  // Printed whether or not anything failed. A note that only appears on failure is a
  // note nobody reads on the runs that matter.
  if (notes.length > 0) {
    console.log(`${notes.length} note(s), for a reader rather than the build:\n`);
    report(notes);
  }

  if (findings.length === 0) {
    console.log("All mechanical checks passed.");
    console.log(
      "\nNote: criteria 1 and 2 (startup-specific, no overlap with Agent Toolkit\n" +
        "for AWS) are judgment calls and are NOT decided here. They remain with\n" +
        "human and agent review. Whether a sunset-service mention above recommends\n" +
        "the service or warns against it is the same kind of judgment, and is left\n" +
        "to the advisory reviewer's staleness axis.",
    );
    return 0;
  }

  report(findings);
  console.log(`${findings.length} violation(s). See solution-architecture/CONTRIBUTING.md.`);
  return 1;
}

try {
  process.exit(main());
} catch (err) {
  console.error(`contribution-gate: harness error: ${err.message}`);
  process.exit(2);
}
