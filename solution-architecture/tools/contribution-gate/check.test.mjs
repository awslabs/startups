/**
 * Tests for the contribution gate.
 *
 * Run: node --test solution-architecture/tools/contribution-gate/check.test.mjs
 *
 * Name the file, do not pass the directory. `node --test <dir>` would also try to run
 * `check.mjs` as a test file, which reports as a failure because it contains no tests.
 *
 * The gate had no tests, which is how it shipped a sunset check that passed three of
 * the four phrasings it existed to catch. A false negative in an enforcement script is
 * invisible by construction: nothing fails, so nobody looks. These fixtures are the
 * cases a reader would assume were already covered.
 *
 * Fixtures are written into a temporary directory and the gate is run with its cwd set
 * there, because the gate resolves paths against `process.cwd()` and only accepts files
 * under `solution-architecture/`. Fixtures committed inside the real tree would be
 * picked up by the gate's own full-tree scan and fail CI.
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const CHECK = join(dirname(fileURLToPath(import.meta.url)), "check.mjs");

/** Run the gate over one markdown body. Returns the criteria it reported. */
function run(markdown) {
  const dir = mkdtempSync(join(tmpdir(), "gate-"));
  const rel = join("solution-architecture", "fixture.md");
  mkdirSync(join(dir, "solution-architecture"), { recursive: true });
  writeFileSync(join(dir, rel), markdown);

  try {
    const out = execFileSync("node", [CHECK, rel], {
      cwd: dir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    return { flagged: false, out };
  } catch (error) {
    // Non-zero exit means findings, which is the interesting case.
    return { flagged: true, out: `${error.stdout ?? ""}${error.stderr ?? ""}` };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** True when the gate noted a sunset-service mention in this markdown. */
const notes = (markdown) => run(markdown).out.includes("[sunset-service]");

/** True when the gate failed the build. */
const failed = (markdown) => run(markdown).flagged;

test("every mention is noted, whatever the phrasing around it", () => {
  // The script no longer tries to tell a recommendation from a warning. Three attempts
  // with cue words failed in both directions: review found six phrasings that
  // recommended a sunset service and passed, because words like `legacy`, `retired`,
  // and `deprecat` exempted the whole line however they were used, and three where a
  // directional phrase exempted the wrong service. Reporting every mention has no
  // false negatives, and notes cannot block, so it has no costly false positives.
  const recommendations = [
    "Use App Runner instead of ECS for a simple container service.",
    "Migrate to App Runner for the fastest path to production.",
    "App Runner is a good default.",
    // Previously exempted by a status word describing something else on the line.
    "We removed the old build script, so use App Runner for the container.",
    "App Runner is a good fit for legacy workloads you do not want to rewrite.",
    "The retired v1 pipeline is gone; deploy with App Runner instead.",
    "Deprecated tooling aside, App Runner is the fastest path to production.",
    // Previously exempted because the directional phrase pointed at another service.
    "Instead of Jenkins, use App Runner.",
    "Migrate off Jenkins and onto App Runner.",
    "Replace the Jenkins box with App Runner.",
  ];
  for (const line of recommendations) {
    assert.ok(notes(line), `should note: ${line}`);
  }
});

test("warnings are noted too, and that is the point", () => {
  // A warning is noted rather than exempted. Nothing is silently dropped, and because
  // notes do not fail the build, noting a legitimate warning costs a reader one line.
  for (const line of [
    "App Runner is deprecated, use ECS instead.",
    "Do not use App Runner for new services.",
    "Migrate away from Cloud9 before it is retired.",
    "Replace App Mesh with ECS Service Connect.",
  ]) {
    assert.ok(notes(line), `should note: ${line}`);
    assert.equal(failed(line), false, `should not fail the build: ${line}`);
  }
});

test("a note never fails the build", () => {
  // The whole reason judgment could leave this script: it can report without blocking.
  assert.equal(failed("App Runner is a good default."), false);
});

test("services that are not sunset are not noted", () => {
  // Each verified against AWS docs rather than assumed, because a list like this rots
  // in the direction that blocks correct advice and a reopening is announced quietly.
  //
  // CodeCommit: closed 2024-07-25, reopened 2025-11-25.
  assert.ok(!notes("Use CodeCommit for a private Git repository close to your CI."));
  // Elastic Beanstalk: the service is current. Only individual platform branches
  // retire, and the AL2023 branches are supported.
  assert.ok(!notes("Deploy the app with Elastic Beanstalk on an AL2023 platform."));
});

test("a renamed service is noted with what it is called now", () => {
  // Only the "for SQL Applications" variant was discontinued. The service itself was
  // renamed, so "this service is gone" would be wrong; the note says which is which.
  const { out } = run("Stream with Kinesis Data Analytics.\n");
  assert.match(out, /Managed Service for Apache Flink/);
  assert.match(out, /for SQL Applications/);
});

test("the note carries the line number of the mention", () => {
  const { out } = run("Fine line.\n\nApp Runner is a good default.\n");
  assert.match(out, /L3/);
});

test("prose with no sunset service is neither noted nor failed", () => {
  const { flagged, out } = run("Use ECS with Fargate for a simple container service.\n");
  assert.equal(flagged, false);
  assert.ok(!out.includes("[sunset-service]"));
});
