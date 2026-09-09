# Example Qualification Patterns

These synthetic examples illustrate the decision method. They are not customer evidence and do not
replace current documentation or a live validation.

## AWS-operated regulated workload

**Situation:** Production inference must be operated by AWS, requests must use private AWS
networking, and the platform team owns IAM and audit evidence.

**First-pass recommendation:** Claude on Amazon Bedrock.

**Smallest useful test:** From the intended VPC and workload role, make one synthetic request to the
exact model and region, then capture endpoint, model access, request ID, and audit evidence.

## AWS purchase with Anthropic-native feature dependency

**Situation:** Anthropic-operated inference is acceptable, purchasing through AWS is preferred, and
the application depends on a current Anthropic-native server tool.

**First-pass recommendation:** Claude Platform on AWS, conditional on the exact model/tool support.

**Smallest useful test:** Run one synthetic request using that server tool through the intended
authentication path. If it is unsupported, decide whether an integration alternative is acceptable
before choosing Bedrock or the direct Anthropic API.

## Direct API feature velocity

**Situation:** A small product team wants the broadest current Anthropic-native API and
administration surface. AWS-operated inference and private networking are not requirements.

**First-pass recommendation:** Anthropic API.

**Smallest useful test:** Verify the critical native capability and the team's key-management,
usage-reporting, and support workflow using synthetic data.

## Multi-model startup platform

**Situation:** The team needs Claude plus other model families, AWS workload identity, centralized
cost controls, and one application gateway. Anthropic-native web search is a preference, not a
must-have.

**First-pass recommendation:** Amazon Bedrock as the model control plane, with a separately
qualified gateway if the operational value justifies it.

**Smallest useful test:** Exercise Claude and one non-Claude model through the proposed gateway,
then verify per-model identity, logs, budgets, failure reporting, and no silent fallback.

## Requirements still unclear

**Situation:** The user says only, "We use AWS and want Claude for an agent."

**First-pass recommendation:** Provisional; do not choose a path yet.

**Ask next:** Whether AWS must operate inference, whether private networking is mandatory, which
native capabilities are decision-critical, and whether the workload needs models beyond Claude.

**Smallest useful test:** None until a disputed assumption is identified. Avoid spending money on
three equivalent hello-world calls that will not change the decision.
