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
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from "node:fs";
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

/**
 * Like `run`, but the caller names the fixture, for path-handling tests.
 *
 * Returns the output only. Both call sites ignored the `flagged` half, and a destructured
 * value nobody reads invites the next reader to assume it is asserted somewhere.
 */
function runNamed(name, markdown, { summary = false } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "gate-"));
  const rel = join("solution-architecture", name);
  mkdirSync(join(dir, "solution-architecture"), { recursive: true });
  writeFileSync(join(dir, rel), markdown);
  const summaryPath = join(dir, "summary.md");
  try {
    return execFileSync("node", [CHECK], {
      cwd: dir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      env: summary ? { ...process.env, GITHUB_STEP_SUMMARY: summaryPath } : process.env,
    });
  } catch (error) {
    return `${error.stdout ?? ""}${error.stderr ?? ""}`;
  } finally {
    if (summary) {
      // Read before the directory goes away, and hand it back on a marker the tests can
      // split on, so one helper covers both emitters.
      try {
        lastSummary = readFileSync(summaryPath, "utf8");
      } catch {
        lastSummary = "";
      }
    }
    rmSync(dir, { recursive: true, force: true });
  }
}

/** Contents of `GITHUB_STEP_SUMMARY` after the most recent `runNamed(..., {summary:true})`. */
let lastSummary = "";

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

test("a note is emitted as a workflow annotation, not only to stdout", () => {
  // Review on awslabs/startups#259: notes printed to the stdout of a passing step are
  // indistinguishable from silence. A green check with notes in collapsed log output
  // reads as "clean" to a contributor, while the summary claimed criterion 3 had been
  // checked. An annotation puts the note on the line in the Files changed view.
  // Three lines, so the asserted line number proves the anchor rather than matching by
  // accident on a single-line fixture.
  const { out } = run("Fine.\n\nApp Runner is a good default.\n");
  assert.match(out, /^::warning file=.*line=3,title=sunset-service::/m);
  const line = out.split("\n").find((l) => l.startsWith("::warning"));

  // Properties are comma-delimited, so `file=` and `line=` must be single-valued and the
  // property segment must carry no stray comma beyond the delimiters.
  const parsed = /^::warning (?<properties>.*?)::(?<data>.*)$/s.exec(line);
  assert.ok(parsed, `annotation did not parse: ${line}`);
  const { properties, data } = parsed.groups;
  assert.match(properties, /^file=[^,]+,line=\d+,title=[^,]+$/);

  // A comma is legal in the DATA segment and is deliberately NOT encoded. An earlier
  // version replaced every comma with a semicolon, which was testing an over-aggressive
  // escape rather than GitHub's spec: only `%`, CR, and LF need encoding in data.
  assert.ok(data.includes(","), "data segment should keep its literal comma");
});

test("a hostile filename cannot inject a workflow command", () => {
  // This gate runs on fork pull requests and git permits newlines, commas, colons, and
  // percent signs in a path. An unencoded path let a contributor emit
  // `::stop-commands::`, which makes Actions ignore every workflow command after it, so
  // one crafted filename silently discarded the annotations for every other file.
  const hostile = "aaa\n::stop-commands::deadbeef\nzz";
  const out = runNamed(`${hostile}.md`, "Cloud9 is here.\n");

  const commandLines = out.split("\n").filter((l) => l.startsWith("::"));
  assert.equal(commandLines.length, 1, `expected one command line, got:\n${out}`);
  assert.match(commandLines[0], /^::warning file=/);
  // Encoded, so the payload is inert text inside the property.
  assert.match(commandLines[0], /%0A%3A%3Astop-commands%3A%3Adeadbeef%0A/);
  assert.equal(out.includes("\n::stop-commands::"), false);
});

test("a comma or colon in a path is encoded so the annotation still anchors", () => {
  const out = runNamed("a,b:c%d.md", "App Runner is here.\n");
  const line = out.split("\n").find((l) => l.startsWith("::warning"));
  assert.match(line, /file=solution-architecture\/a%2Cb%3Ac%25d\.md,line=1,/);
});

test("a real violation still fails the build", () => {
  // Mutation check. Every other use of `failed()` asserts false, so flipping the script's
  // final `return 1` to `return 0` left all tests green: the entire enforcing half had no
  // coverage. An em dash is the cheapest violation to assert on.
  assert.equal(failed("A sentence with an em dash \u2014 right here.\n"), true);
});

test("supplied paths that all get filtered out is an error, not a pass", () => {
  // Bare `xargs` word-splits, so a changed path containing a space arrived as fragments
  // that failed `existsSync` and vanished. "Every argument discarded" was then reported
  // the same as "nothing to check", shipping the violation behind a green check.
  const dir = mkdtempSync(join(tmpdir(), "gate-"));
  mkdirSync(join(dir, "solution-architecture"), { recursive: true });
  try {
    execFileSync("node", [CHECK, "solution-architecture/does-not-exist.md"], {
      cwd: dir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    assert.fail("expected a non-zero exit");
  } catch (error) {
    assert.equal(error.status, 2);
    assert.match(`${error.stderr}`, /none survived filtering/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("annotations are emitted for every note, not just the first", () => {
  const { out } = run("Use App Runner today.\n\nCloud9 is fine too.\n");
  assert.equal(out.split("\n").filter((l) => l.startsWith("::warning")).length, 2);
});

test("a violation is annotated too, not only the notes that cannot block", () => {
  // Review on awslabs/startups#259: the notes path emitted annotations AND a step summary,
  // justified by "stdout alone was indistinguishable from silence". Violations got neither,
  // so a contributor saw a red X and had to expand collapsed logs to find the file and
  // line. The fix that was applied to the half that cannot block had skipped the half that
  // does.
  const { out } = run("Fine.\n\nAn em dash — right here.\n");
  const line = out.split("\n").find((l) => l.startsWith("::error"));
  assert.ok(line, `expected an ::error annotation, got:\n${out}`);
  assert.match(line, /^::error file=solution-architecture\/fixture\.md,line=3,title=style::/);
});

test("a violation writes a step summary, which is where a red check is read", () => {
  runNamed("bad.md", "An em dash — right here.\n", { summary: true });
  assert.match(lastSummary, /### Contribution gate: 1 violation\(s\)/);
  assert.match(lastSummary, /`solution-architecture\/bad\.md:1`/);
  assert.match(lastSummary, /\[style\]/);
});

test("a hostile filename cannot inject markdown into the step summary", () => {
  // The summary used a second, divergent sanitiser: it stripped backticks and newlines
  // while the annotations encoded them. Stripping was inert but silently misreported the
  // filename, and two escaping rules for one untrusted value is how the next emitter gets
  // the weaker one. Both now encode.
  //
  // A heading needs to be at column 0, and a code span needs a bare backtick to close it,
  // so those are the two characters asserted on. `#` itself is left alone: encoding it
  // would be theatre once the newline cannot survive.
  const hostile = "aaa\n# INJECTED HEADING\nzz`x";
  runNamed(`${hostile}.md`, "Cloud9 is here.\n", { summary: true });

  assert.ok(lastSummary.length > 0, "expected a summary to be written");
  assert.match(lastSummary, /%0A# INJECTED HEADING%0A/);
  // The gate's own `### Contribution gate` heading is legitimate, so assert on the
  // payload's heading specifically rather than on any line starting with `#`.
  assert.equal(
    lastSummary.split("\n").some((l) => l.startsWith("# INJECTED")),
    false,
    `payload reached column 0:\n${lastSummary}`,
  );
  // The backtick is encoded, so the filename cannot close its own code span.
  assert.match(lastSummary, /zz%60x\.md/);
  assert.equal(lastSummary.split("\n").filter((l) => l.startsWith("- `")).length, 1);
});

test("lowercase prose about launch configurations is still noted", () => {
  // Scoping this entry to Auto Scaling correctly dropped the bare-phrase false positives,
  // but it also switched the whole alternation to `/g`, so the prose form stopped matching
  // lowercase while every other entry in SUNSET stayed `/gi`. The identifiers keep `/g`
  // because their casing is exact.
  assert.ok(notes("Do not use auto scaling launch configurations for new groups."));
  assert.ok(notes("Replace CreateLaunchConfiguration with CreateLaunchTemplate."));
  assert.ok(notes("The AWS::AutoScaling::LaunchConfiguration resource is blocked."));
});
