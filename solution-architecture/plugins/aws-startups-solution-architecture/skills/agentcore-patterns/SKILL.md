---
name: agentcore-patterns
description: "Use when running an Amazon Bedrock AgentCore agent that makes judgment calls inside an engineering pipeline, such as an LLM reviewer, judge, or quality gate, and the team has no platform engineer to operate it. Covers deciding which findings may block a merge, measuring verdict stability before an agent gates anything, confidence banding so borderline findings surface instead of vanishing, grounding the model in facts computed by code, and the cost and session settings that bite. Also use when such an agent is deployed but its verdicts are unstable, its findings are being ignored, or a deployed fix does not appear to be running. Not for building, deploying, or hardening an agent, which belong to the aws-agents skills upstream, or for runtime selection and model choice."
license: Apache-2.0
metadata:
  audience: startup
---

# AgentCore Patterns

Apply these patterns to agents that act inside an engineering pipeline rather than serving end users. Upstream `aws-agents` owns the build, deploy, and hardening mechanics. What it does not cover is the judgment layer, which is where these agents actually fail.

Treat one constraint as primary: nobody is available to babysit the agent. A judge that is wrong, slow, or noisy will not be tuned over a quarter by a platform team. It gets ignored, and then it is worse than nothing, because it occupies the slot where review attention used to be.

Design for that outcome. Measure stability before granting an agent authority to block, report a stance on every axis so silence is never ambiguous, and compute in code anything the judgment depends on.

## Reference files

- **`references/git-code-reviewer-agent.md`**: Read before letting any agent gate a merge. Field notes from running a pull-request reviewer on this repository: which finding kinds may block, measured verdict stability across repeated runs of one unchanged pull request, three-band confidence reporting, grounding the model in code-computed facts, keeping the harness from misleading the model, and the cost and warm-container behavior that make a deployed fix appear not to run.

## Upstream skills to defer to

Do not restate the mechanics these own. Invoke them directly:

- **`Skill("aws-agents:agents-build")`**: Agent construction, tools, prompts, memory, and multi-agent composition.
- **`Skill("aws-agents:agents-deploy")`**: Container contract, deployment, versioning, rollback, and deploy-failure diagnosis.
- **`Skill("aws-agents:agents-harden")`**: IAM scoping, inbound auth, secret handling, session lifecycle, and quotas.
- **`Skill("aws-agents:agents-debug")`**: Traces, logs, and diagnosis of a deployed agent.
- **`Skill("aws-agents:agents-optimize")`**: Latency and token-cost tuning of an existing agent.
- **`Skill("aws-core:amazon-bedrock")`**: Model invocation, prompt caching, and throttling diagnosis.
- **`Skill("aws-core:aws-ai-ml")`**: Model selection and inference-cost comparison.

For runtime selection before any of this applies, such as AgentCore against Lambda or ECS, use `Skill("aws-startup-advisor:agent-advisor")`.
