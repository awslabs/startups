---
name: agentcore-patterns
description: "Running an AgentCore agent that makes judgment calls inside your own CI path, for a team with nobody to babysit it. Covers deciding which agent findings may block a merge, measuring verdict stability before letting one gate anything, confidence banding so borderline findings surface instead of vanishing, grounding the model in facts computed by code, and the cost settings that matter. Use when standing up or debugging an LLM reviewer, judge, or gate in a pipeline, or when its verdicts are unstable, noisy, or being ignored. Triggers on: agentcore code reviewer, LLM judge in CI, agent reviews pull requests, reviewer verdict flip-flops, agent findings ignored, confidence threshold tuning, agent reports wrong line numbers, warm container running old code. Not for: building or deploying an agent generally (use agents-build and agents-deploy in aws-agents), IAM and session hardening (use agents-harden), or model selection (use amazon-bedrock in aws-core)."
metadata:
  audience: startup
---

# AgentCore Patterns

Patterns for agents that act inside your own engineering pipeline rather than serving your customers. The build and deploy mechanics belong upstream in `aws-agents`; what is not covered there is the judgment layer, which is where these agents actually fail.

The startup constraint that shapes all of it: there is nobody to babysit the agent. A judge that is wrong, slow, or noisy does not get tuned over a quarter by a platform team. It gets ignored, and then it is worse than nothing, because it occupies the slot where review attention used to be.

## References

| Task                                                                                                                                                                                | Reference                                                           |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Running a judgment agent in your CI path: what it may block, measuring verdict stability, confidence bands, grounding it in computed facts, cost shape and warm-container staleness | [git-code-reviewer-agent.md](references/git-code-reviewer-agent.md) |

## Where the rest comes from

- Container contract, deploy, versioning, rollback: `agents-deploy` in `aws-agents`.
- IAM scoping, inbound auth, secrets, session lifecycle, quotas: `agents-harden` in `aws-agents`.
- Memory, VPC, multi-agent composition: `agents-build` in `aws-agents`.
- Debugging a deployed agent, traces and logs: `agents-debug` in `aws-agents`.
- Model choice and inference cost: `amazon-bedrock` and `aws-ai-ml` in `aws-core`.
- Choosing a runtime at all (AgentCore vs Lambda vs ECS): `agent-advisor` in AWS Startup Advisor.
