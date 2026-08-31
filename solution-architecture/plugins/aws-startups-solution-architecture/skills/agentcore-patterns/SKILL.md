---
name: agentcore-patterns
description: "This skill should be used when deciding whether an automated agent's verdict may carry authority over someone else's merge, and how to publish it so reviewers trust it rather than route around it. Covers which finding kinds may block versus advise, why an unstable verdict must not gate, surfacing borderline items instead of dropping them, grounding claims in facts computed by code rather than recalled, and the review-state and memory behaviour that decides whether contributors keep reading the output. It should also be used when such an agent is being ignored, contradicts itself between runs, or reports a state that no current review supports. Not for measuring or improving an agent's own output quality, which belongs to aws-agents:agents-optimize, nor for building, deploying, or hardening an agent."
license: Apache-2.0
metadata:
  audience: startup
---

# AgentCore Patterns

Apply these patterns to agents that act inside an engineering pipeline rather than serving end users. Upstream `aws-agents` owns the build, deploy, and hardening mechanics. What it does not cover is the judgment layer, which is where these agents actually fail.

Treat one constraint as primary: nobody is available to babysit the agent. A judge that is wrong, slow, or noisy will not be tuned over a quarter by a platform team. It gets ignored, and then it is worse than nothing, because it occupies the slot where review attention used to be.

Design for that outcome. Measure stability before granting an agent authority to block, report a stance on every axis so silence is never ambiguous, and compute in code anything the judgment depends on.

## Reference files

- **`references/git-code-reviewer-agent.md`**: Read before letting any agent gate a merge. End-to-end wiring for a pull-request reviewer: why the credential identity decides whether a verdict can be recorded at all, why the reviewer must read the diff through the API rather than check it out, why the obvious CI trigger cannot reach a credentialed runtime, which finding kinds may block a merge, how to measure verdict stability before granting that authority, why a second pass that never saw the argument for a finding is what fixes the cause rather than the symptom, three-band confidence reporting, why the replies on a pull request have to be read and why they are still untrusted input, how settled rulings accumulate in memory instead of being hand-written into a prompt, how to load the team's own plugins and skills as the reviewer's rubric instead of letting it recall conventions from memory, why the submitted review state must match what the body says and why stale approvals have to be retracted rather than merely superseded, how to write findings for the narrow column a review comment renders in, and the warm-container behavior that makes a deployed fix appear not to run.

## Upstream skills to defer to

Do not restate the mechanics these own. Invoke them directly:

- **`Skill("aws-agents:agents-build")`**: Agent construction, tools, prompts, memory, and multi-agent composition.
- **`Skill("aws-agents:agents-deploy")`**: Container contract, deployment, versioning, rollback, and deploy-failure diagnosis.
- **`Skill("aws-agents:agents-harden")`**: IAM scoping, inbound auth, secret handling, session lifecycle, and quotas.
- **`Skill("aws-agents:agents-debug")`**: Traces, logs, and diagnosis of a deployed agent.
- **`Skill("aws-agents:agents-optimize")`**: Evaluators, online monitoring, CI/CD quality gates, observability, and latency and token-cost tuning. **Read this first if the goal is to measure an agent's quality.** It owns the evaluator and quality-gate machinery; this skill covers only the narrower case where the agent _is_ the gate, and the question is whether its verdicts are stable enough to carry authority.
- **`Skill("aws-core:amazon-bedrock")`**: Model invocation, prompt caching, and throttling diagnosis.
- **`Skill("aws-core:aws-ai-ml")`**: Model selection and inference-cost comparison.

For runtime selection before any of this applies, such as AgentCore against Lambda or ECS, use `Skill("aws-startup-advisor:agent-advisor")`.
