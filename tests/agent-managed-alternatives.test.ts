import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";

const PLUGINS = [
  "migrate/plugins/migration-to-aws",
  "advisor/plugins/aws-startup-advisor",
];

function read(plugin: string, file: string): string {
  return readFileSync(
    join(plugin, "skills/agent-advisor/references", file),
    "utf8",
  );
}

function section(text: string, heading: string): string {
  const start = text.indexOf(`## ${heading}\n`);
  assert.notEqual(start, -1, `missing section: ${heading}`);
  const bodyStart = start + `## ${heading}\n`.length;
  const end = text.indexOf("\n## ", bodyStart);
  return text.slice(bodyStart, end === -1 ? undefined : end).trim();
}

for (const plugin of PLUGINS) {
  describe(`${plugin}: managed agent alternatives`, () => {
    const card = read(plugin, "decision-refs/managed-alternatives.md");
    const design = read(plugin, "phases/design/design.md");
    const generate = read(plugin, "phases/generate/generate.md");
    const report = read(plugin, "phases/generate/generate-report.md");

    it("keeps the Bedrock region and recommendation in the Bedrock section", () => {
      const bedrock = section(card, "Bedrock Managed Agents (OpenAI-committed)");
      const openai = section(card, "OpenAI Agents API (public beta)");
      assert.match(bedrock, /Available in us-east-1 and expanding/);
      assert.match(bedrock, /model flexibility, governance, or code export/);
      assert.doesNotMatch(openai, /us-east-1|AgentCore wins/);
    });

    it("grounds the new offering's boundary in current vendor documentation", () => {
      const openai = section(card, "OpenAI Agents API (public beta)").replace(/\s+/g, " ");
      assert.match(openai, /2026-09-10/);
      assert.match(openai, /United States/);
      assert.match(openai, /does not support Zero Data Retention/);
      assert.match(openai, /self-hosted sandbox does not remove these limits/);
      assert.match(openai, /OpenAI still runs the harness/);
      assert.match(openai, /developers\.openai\.com\/api\/docs\/guides\/agents-api\/overview/);
      assert.match(openai, /developers\.openai\.com\/api\/docs\/guides\/agents-api\/environments\/security/);
    });

    it("records both OpenAI options without changing the legacy provider mapping", () => {
      const lockIn = section(design, "Step 4 — Provider lock-in check");
      const rows = lockIn.split("\n").filter((line) => line.startsWith("| "));
      const expected = [
        ["Claude-committed", ["claude_managed"], "claude_managed"],
        ["OpenAI-committed", ["bedrock_managed", "openai_agents_api"], "bedrock_managed"],
        ["Multi-provider or undecided", [], "none"],
      ] as const;
      for (const [provider, ids, legacy] of expected) {
        const row = rows.find((line) => line.split("|")[1].trim() === provider);
        assert.ok(row, `missing provider row: ${provider}`);
        const cells = row.split("|").slice(1, -1).map((cell) => cell.trim().replaceAll("`", ""));
        assert.deepEqual(JSON.parse(cells[1]), ids);
        assert.equal(cells[2], legacy);
      }
      assert.match(design, /"managed_alternatives":/);
      assert.match(design, /"managed_alternative": "claude_managed \| bedrock_managed \| none"/);
    });

    it("carries awareness into the document and report without treating it as scoring", () => {
      assert.match(generate, /managed_alternatives/);
      assert.match(generate, /Only when the array is absent/);
      assert.match(generate, /An explicitly empty array stays empty/);
      assert.match(generate, /decision-refs\/managed-alternatives\.md/);
      assert.match(generate, /Section 5 — Managed alternatives/);
      assert.match(generate, /do not add these options to scores or the runtime ranking/);
      const brief = section(
        generate,
        "Step 4.5 — Write the mini-brief to `$RUN_DIR/mini-brief.md` (delivered by the Step 5.5 sidebar)",
      );
      assert.match(brief, /managed alternatives/);
      assert.match(brief, /public-beta, US-only, and no-ZDR/);
      assert.match(report, /MANAGED_ALTERNATIVES_HTML[\s\S]*recommendation\.md §5/);
      assert.match(report, /IF MANAGED_ALTERNATIVES_HTML/);
      assert.match(report, /Managed alternatives \(awareness only\)/);
    });
  });
}
