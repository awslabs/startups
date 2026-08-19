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
  { pattern: /\bKinesis Data Analytics\b/gi, name: "Kinesis Data Analytics" },
  { pattern: /\bElastic Beanstalk\b/gi, name: "Elastic Beanstalk" },
  { pattern: /\bAurora Serverless v1\b/gi, name: "Aurora Serverless v1" },
  { pattern: /\blaunch configuration/gi, name: "EC2 launch configurations" },
  { pattern: /\bCodeCommit\b/gi, name: "AWS CodeCommit" },
  { pattern: /\bCloud9\b/gi, name: "AWS Cloud9" },
  { pattern: /\bSimpleDB\b/gi, name: "Amazon SimpleDB" },
];

// A sunset mention is permitted when the surrounding line frames it as a
// warning, a deprecation note, or a migration away from the service.
const WARNING_CUE =
  /\b(deprecat|sunset|end of support|end-of-support|closed to new|do not|don't|avoid|instead of|migrat|no longer|retir|legacy|EOL|rather than|not for new|stop)/i;

const findings = [];
const add = (file, criterion, line, message) =>
  findings.push({ file, criterion, line, message });

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
      const line = lines[lineNo - 1] ?? "";
      if (WARNING_CUE.test(line)) continue; // warned about, not recommended
      add(
        rel,
        "sunset-service",
        lineNo,
        `References ${name} without a deprecation or migration caveat. Warning against it is fine; recommending it is not.`,
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

  if (findings.length === 0) {
    console.log("All mechanical checks passed.");
    console.log(
      "\nNote: criteria 1 and 2 (startup-specific, no overlap with Agent Toolkit\n" +
        "for AWS) are judgment calls and are NOT decided here. They remain with\n" +
        "human and agent review.",
    );
    return 0;
  }

  const byFile = new Map();
  for (const f of findings) {
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
  console.log(`${findings.length} violation(s). See solution-architecture/CONTRIBUTING.md.`);
  return 1;
}

try {
  process.exit(main());
} catch (err) {
  console.error(`contribution-gate: harness error: ${err.message}`);
  process.exit(2);
}
