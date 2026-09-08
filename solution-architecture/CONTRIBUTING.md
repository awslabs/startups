# Contributing to `solution-architecture/`

This folder is open to contribution. It is also the folder whose previous plugin, `aws-dev-toolkit`, was removed because its content had grown into a duplicate of [Agent Toolkit for AWS](https://github.com/aws/agent-toolkit-for-aws). The gate below exists so that does not happen again.

Read the [root contributing guide](../CONTRIBUTING.md) for code of conduct, security reporting, and licensing. This document adds the content gate specific to this folder.

## Start with an RFC, before you write the skill

A new skill is a new artifact, so the root guide's [RFC requirement](../CONTRIBUTING.md#rfcs-for-new-features-artifacts-and-major-changes) applies: open an [RFC issue](https://github.com/awslabs/startups/issues/new/choose) titled `RFC: <what you want to add>` before doing the work.

Do this first because criterion 2 below rejects more proposals than any other, and it is far cheaper to find out that Agent Toolkit for AWS already owns your topic in an issue thread than after you have written the skill. State in the RFC:

- The technical problem, and the startup constraint that changes the answer.
- What you checked for overlap: the specific upstream skills in `aws-core` and `aws-agents`, and the relevant AWS Startup Advisor content.
- Why the answer differs from what a reviewer would find in those places.

## The gate: all three criteria must pass

A contribution is accepted only if it passes **all three**. Two out of three is a rejection, not a majority.

### 1. Startup-specific, not general-purpose AWS

This folder is for **technical architecture and AWS problem solving**, where the technical constraints are startup constraints: no dedicated platform or security team, a fixed cost ceiling that is someone's runway, capacity that cannot be committed to for years, and a deadline that is a funding milestone. Those constraints change the correct technical answer, and that difference is what belongs here.

General-purpose AWS service guidance that would read identically for a large, established company fails this criterion and belongs in Agent Toolkit for AWS. This is the criterion that keeps the folder from re-accumulating the general-purpose content that caused the previous removal.

**Founder coaching, stage-appropriateness advice, and business guidance also fail this criterion.** Stage detection, runway math, AWS Activate, credits strategy, and fundraise readiness belong in [AWS Startup Advisor](../advisor/), not here. Startup constraints are an input to the technical answer; they are not the subject.

**Referencing AWS products and services is expected and allowed.** The test is whether the problem is a real technical problem that startup constraints reshape.

| Passes                                                                    | Fails                                                                 |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| Tenant isolation enforced in IAM because there is no security engineer    | How to write an IAM policy (belongs in `aws-iam` upstream)            |
| Securing scarce GPU capacity without a multi-year commitment              | Which GPU instance family is fastest (belongs in `aws-compute`)       |
| Scale-to-zero because an idle environment must cost approximately nothing | "Start simple and scale later" as general advice                      |
| Cost regression caught in the deploy path before the monthly bill         | Whether the company is ready to raise a Series A (belongs in advisor) |

### 2. No overlap with Agent Toolkit for AWS

If Agent Toolkit for AWS already covers the capability, the contribution is a duplicate and fails.

**This is the load-bearing check**, because overlap is the conflict that drove the previous deprecation. Before contributing, check the upstream skill list in [`aws-core`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-core/skills) and [`aws-agents`](https://github.com/aws/agent-toolkit-for-aws/tree/main/plugins/aws-agents/skills). Those plugins are declared as upstream dependencies, so their skills are already available to anyone who installs from this folder. Restating them here is strictly worse than depending on them.

Also check [AWS Startup Advisor](../advisor/) for overlap, particularly its `architect-for-startups` skill and that skill's `references/` directory, which already covers a broad set of startup-framed architecture topics. Founder-facing stage advice, AWS Activate, and credits guidance live there, not here.

**This is judged at the discovery surface.** `SKILL.md` is the only file Claude Code discovers, and its description decides what gets loaded. A description claiming a capability upstream already owns creates two front doors to one topic: they compete for activation, the model may load the local one instead of the authoritative one, and they drift. That is the failure that removed the previous plugin here.

Files under `references/` have no discovery surface. They load only because a `SKILL.md` linked them, so a reader has already chosen the skill. Prose there that restates upstream mechanics as context is not duplication, it is how a readable reference is written, and it is not grounds for rejection. The exception is wholesale reproduction of an upstream skill's substance, which is a maintenance burden worth avoiding but not a routing collision.

Do not use the word "toolkit" in a plugin, skill, or agent name in this folder.

### 3. No deprecated or sunset AWS services

Contributions must not reference, recommend, or depend on AWS services that are deprecated, sunset, or closed to new customers.

Naming a sunset service in order to warn against it, or to describe a migration away from it, is fine. Recommending one as a forward-looking choice is not. Verify current status against AWS documentation rather than from model memory, which reproduces retired service names and deprecated constructs from stale training data.

## Make "startup-specific" explicit, not inferred

A reviewer should not have to infer startup-specificity from prose. Declare it so the check is deterministic and auditable.

- **Required frontmatter field.** Every `SKILL.md` in this folder must declare `audience: startup` under `metadata`:

  ```yaml
  ---
  name: your-skill
  description: "..."
  metadata:
    audience: startup
  ---
  ```

- **Name the problem and the constraint in the description.** State the technical problem being solved and the startup constraint that reshapes the answer. `multi-tenant-isolation` names isolation enforced in IAM rather than application code, because there is no security engineer to catch a missing predicate in review. That is the shape: a real technical problem, plus why the small-team answer differs.

- **Do not keyword-stuff.** Startup vocabulary (`runway`, `credits`, `stage`, `activate`) belongs in a description only where it is genuinely load-bearing. `multi-tenant-isolation` uses none of those words and is the stronger skill in this folder. A skill that sprinkles "runway" to look startup-specific while otherwise being general service guidance fails criterion 1 on review.

  A worked rejection: a `gpu-capacity-strategy` skill was proposed and removed during review. It used runway and credits correctly, but the substance was a commitment-versus-observed-usage ladder that any team without procurement authority faces identically, whatever the size of the company. Naming the startup constraint is not the same as the constraint changing the answer, and that distinction is what criterion 1 tests.

- **Generalize the triggers; do not list every query.** Describe categories of intent rather than an expanding list of near-verbatim phrases. The goal is not an ever-expanding list of specific queries a skill should or should not fire on, but to generalize to broader categories of user intent.

- **Write the description in the third person, opening with `This skill should be used when`.** State the situation the skill applies to, then what it covers, then what it is not for. Keep it to roughly 100 to 200 words. The hard limit is 1024 characters and text over it is truncated.

  Published authoring guidance is not unanimous here: some of it prescribes an imperative form (`Use when...`) instead. Third person is the convention for this folder, so that skills read consistently with the wider plugin authoring guidance and with the automated checks built on it. Apply it consistently.

- **Do not add `when_to_use` or `version`.** `when_to_use` is deprecated in favour of `description`, so all triggering information belongs there, and the skill validator rejects `version` outright. Allowed fields are `name`, `description`, `license`, `allowed-tools`, `metadata`, and `compatibility`.

- **Write the body in the imperative, not the second person.** "Apply these patterns to agents that..." rather than "you should apply these to your agents." Reference files may keep a field-note voice; `SKILL.md` should not.

The `audience: startup` field is the only mechanical signal, and it is deliberately weak: any file can declare it. Criteria 1 and 2 are judged on substance by a reviewer, and that is the point. The field exists so a missing declaration is caught automatically, not so a present one proves anything.

## Skill and reference file layout

Depth belongs in reference files. A `SKILL.md` works best as a thin router that tells the model when to activate and which reference to open, with the substance living alongside it:

```text
skills/<skill-name>/
  SKILL.md                       # required: router + frontmatter
  references/<topic>.md           # the actual depth
  references/<another-topic>.md
```

This is the documented pattern, not a local invention. From the [skills documentation](https://code.claude.com/docs/en/skills): "Skills can include multiple files in their directory. This keeps `SKILL.md` focused on the essentials while letting Claude access detailed reference material only when needed." It also sets the ceiling: "Keep `SKILL.md` under 500 lines. Move detailed reference material to separate files."

Three structural rules, verified against all 32 upstream Agent Toolkit skills:

1. **Every skill directory needs a `SKILL.md`.** It is the only file Claude Code discovers, and its frontmatter `description` is what the model matches to decide whether the skill applies. A `references/` directory with no sibling `SKILL.md` is invisible.
2. **Reference files are never auto-loaded.** They are read on demand _because `SKILL.md` links to them_. A file in `references/` that nothing links to will never be opened, so the gate flags it as an orphan.
3. **Only `SKILL.md` carries frontmatter requirements.** Reference files need no `name`, `description`, or `audience` field. Do not add them.

Nesting deeper is allowed (`references/<topic>/references/<subtopic>.md`) and upstream does this where a topic has genuine sub-branches.

Link reference files with a bolded backticked path, then a dash, then when to read it. This is the shape the official authoring guidance prescribes:

```markdown
## Reference files

- **`references/git-code-reviewer-agent.md`**: Read before letting any agent gate a merge. Covers ...
```

**Make upstream pointers invocable.** When the answer lives upstream, write it as a callable skill reference rather than prose, so a model can act on the pointer instead of guessing a name:

```markdown
- **`Skill("aws-agents:agents-deploy")`**: Container contract, deployment, versioning, rollback.
```

Every such pointer must name a skill that actually exists. The gate verifies this, because a plugin whose whole premise is deference is worthless if its pointers are wrong.

## What we are actively looking for

The plugin README carries a [list of verified gaps](plugins/aws-startups-solution-architecture/README.md#what-to-contribute): topics confirmed to be covered by neither Agent Toolkit for AWS nor AWS Startup Advisor, each a recurring startup engagement problem. Self-hosted inference serving is the largest one open today.

Bring your own topic if it passes the scope test above. The existing skills are the intended shape and depth: decision tables, the failure mode named explicitly, an anti-pattern list, and service mechanics delegated upstream rather than restated.

## Prefer an upstream dependency over a copy

If a capability exists in Agent Toolkit for AWS, declare it as a dependency rather than vendoring it. See [plugin dependencies](https://code.claude.com/docs/en/plugin-dependencies).

Dependencies on plugins in `claude-plugins-official` require that marketplace to be listed in `allowCrossMarketplaceDependenciesOn` in the root `.claude-plugin/marketplace.json`, which it already is. Note that a semver constraint on those dependencies will fail to resolve until the upstream repository publishes `{plugin-name}--v{version}` git tags, so declare them unversioned for now.

## Before opening a PR

Run these and confirm each is clean. CI fails the build if formatting changes any file, so formatting is not optional.

```bash
mise run fmt          # must leave the tree unchanged
mise run lint:md      # must report 0 errors

claude plugin validate ./solution-architecture/plugins/<your-plugin>
claude plugin validate .   # only if you touched marketplace.json
```

If `mise` fails while installing its npm tools with a `401` or `Unable to authenticate`, that is a local npm registry problem rather than a repo problem: check whether `~/.npmrc` points at an internal registry with an expired token. You can run the same gates directly in the meantime:

```bash
npx dprint@0.51 fmt
npx markdownlint-cli2@0.17 'solution-architecture/**/*.md'
```

Then, for a new plugin or a dependency change, prove it actually installs rather than assuming the manifest is enough:

```bash
claude plugin marketplace add /path/to/your/clone
claude plugin install <your-plugin>@startups-for-aws
claude plugin list          # confirm enabled, no dependency errors
# then clean up:
claude plugin uninstall <your-plugin>@startups-for-aws -y
claude plugin marketplace remove startups-for-aws
```

A passing `validate` does not prove dependencies resolve. Cross-marketplace dependency errors only surface at install time.

Then run the gate itself. CI runs exactly this on every PR touching `solution-architecture/`:

```bash
node solution-architecture/tools/contribution-gate/check.mjs
```

Across **every markdown file** in this folder, including reference files, it checks for uncaveated sunset-service references and prose style. The removed `aws-dev-toolkit` recommended App Mesh in `references/compute.md` and App Runner in `references/cost-comparison.md`, so reference files are where this problem has actually shown up rather than a hypothetical.

On `SKILL.md` specifically it additionally checks the `audience: startup` declaration, required frontmatter fields, banned naming, and reference files that no `SKILL.md` links to.

It requires no credentials and no AWS access, so it also runs on pull requests from forks.

**It does not decide criteria 1 and 2.** Whether a contribution is genuinely startup-specific, and whether it overlaps Agent Toolkit for AWS, are judgment calls that a script cannot settle. Those stay with reviewers, so a green gate means "nothing mechanically wrong," not "accepted."

On sunset services the check is context-aware: warning against one or describing a migration off it passes, while recommending one as a forward-looking choice fails. If you get a false positive, phrase the line as the warning it presumably is rather than working around the check.

## Review

A pull request here needs approval from the Solution Architecture team. Changes to `marketplace.json`, any `SKILL.md`, or a plugin manifest additionally need admin approval. See [CODEOWNERS](../.github/CODEOWNERS) for the current routing.

Automated checks run on every pull request that touches this folder, and passing them is necessary rather than sufficient. They decide nothing about criteria 1 and 2, so a green run means only that nothing mechanically wrong was found.

An automated reviewer that comments on criteria 1 and 2 is in development. Treat its output as advice: it does not approve on the team's behalf, and a human still decides.
