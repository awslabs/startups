---
name: agentcore-patterns
description: "This skill should be used when an automated agent's output is published under its own identity and carries weight in someone else's work, such as a reviewer whose verdict lands on a pull request, and the open question is how much authority it has actually earned. Covers which conclusions such an agent may state as settled and which it must hand to a person, why a verdict that moves between runs on unchanged input cannot be allowed to decide anything, handing an uncertain item to a human rather than discarding it, grounding each claim in something computed rather than recalled, and the published-state and recall behaviour that decides whether people keep reading the output or learn to skim it. It should also be used when such an agent is being ignored, contradicts itself between runs, or reports a state that nothing current supports. Not for measuring or improving an agent's own output quality, which belongs to aws-agents:agents-optimize, nor for building, deploying, or hardening an agent."
license: Apache-2.0
metadata:
  audience: startup
---

# AgentCore Patterns

Apply these patterns to agents that act inside an engineering pipeline rather than serving end users. Upstream `aws-agents` owns the build, deploy, and hardening mechanics. What it does not cover is the judgment layer, which is where these agents actually fail.

Treat one constraint as primary: nobody is available to babysit the agent. A judge that is wrong, slow, or noisy will not be tuned over a quarter by a platform team. It gets ignored, and then it is worse than nothing, because it occupies the slot where review attention used to be.

Design for that outcome. Measure stability before granting an agent authority to block, report a stance on every axis so silence is never ambiguous, and compute in code anything the judgment depends on.

## Reference files

- **`references/git-code-reviewer-agent.md`**: Read before letting any agent's output
  carry weight in someone else's work. End-to-end wiring for a pull-request reviewer,
  from the credential identity that decides whether a verdict can be recorded at all,
  through reading the pull request as data, the trigger that reaches a credentialed
  runtime, what the agent should remember between runs, and the judgment design that
  decides whether anyone keeps reading the output. Written as field notes, including
  the failures.

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
