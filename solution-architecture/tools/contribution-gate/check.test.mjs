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

const flags = (markdown) => run(markdown).out.includes("[sunset-service]");

test("recommending a sunset service is caught however it is phrased", () => {
  // Every one of these passed before the cue lists were split. `instead of`, `migrat`,
  // and `avoid` were treated as warnings wherever they sat on the line, so the words
  // that appear when recommending a service exempted the recommendation.
  assert.ok(flags("Use App Runner instead of ECS for a simple container service."));
  assert.ok(flags("Migrate to App Runner for the fastest path to production."));
  assert.ok(flags("Prefer CodeCommit over GitHub to avoid a third-party dependency."));
  assert.ok(flags("App Runner is a good default."));
});

test("warning about a sunset service is still allowed", () => {
  // The check must not fire on the prose it exists to encourage. A status word anywhere
  // on the line is unambiguous; a directional phrase counts only before the name.
  assert.ok(!flags("App Runner is deprecated, use ECS instead."));
  assert.ok(!flags("Do not use App Runner for new services."));
  assert.ok(!flags("Migrate away from CodeCommit before it is retired."));
  assert.ok(!flags("Avoid CodeCommit; it is closed to new customers."));
  assert.ok(!flags("Replace App Mesh with ECS Service Connect."));
  assert.ok(!flags("App Mesh is retired, so use ECS Service Connect."));
});

test("a directional phrase after the service name does not exempt it", () => {
  // The line-scoped cue meant any cue word anywhere granted an exemption, so a
  // recommendation followed by an unrelated "avoid" or "instead of" passed.
  assert.ok(flags("Choose App Runner, and avoid managing servers yourself."));
  assert.ok(flags("Pick CodeCommit rather than paying for a third-party host."));
});

test("the gate reports the line number of the offending mention", () => {
  const { out } = run("Fine line.\n\nApp Runner is a good default.\n");
  assert.match(out, /L3/);
});

test("prose with no sunset service passes", () => {
  const { flagged } = run("Use ECS with Fargate for a simple container service.\n");
  assert.equal(flagged, false);
});
