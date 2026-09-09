# Claude Access-Path Decision Guide

**Last reviewed:** 2026-09-09

This reference distinguishes operating and commercial boundaries before comparing features. Product
names and feature availability can change; use the linked public documentation for a decision that
depends on a current capability.

## The three paths

| Path                     | Inference operator | Typical control and commercial boundary                                           | Start here when                                                                                               |
| ------------------------ | ------------------ | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Anthropic API            | Anthropic          | Direct Anthropic API, organization, workspace, keys, usage, and billing           | Direct Anthropic ownership and current Anthropic-native APIs or administration matter most                    |
| Claude Platform on AWS   | Anthropic          | Claude Platform connected to AWS commercial and supported AWS identity paths      | The team wants Anthropic-operated Claude APIs with an AWS purchasing or identity relationship                 |
| Claude on Amazon Bedrock | AWS                | Amazon Bedrock endpoints, AWS IAM, AWS service controls, and Bedrock model access | AWS-operated inference, private AWS networking, multi-model AWS access, or AWS-native governance is mandatory |

Public overviews:

- [Build with Claude overview](https://platform.claude.com/docs/en/build-with-claude/overview)
- [Claude Platform on AWS](https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws)
- [Claude on Amazon Bedrock](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- [What is Amazon Bedrock?](https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html)

## Questions that can change the answer

Ask only the unresolved questions that separate the remaining paths.

### Operating boundary

1. Must inference be operated by AWS, or is Anthropic-operated inference acceptable?
2. Must traffic remain on private AWS networking?
3. Which team must own identity, audit evidence, quota changes, and incident escalation?

If AWS-operated inference or Amazon Bedrock VPC endpoints are hard requirements, the Anthropic API
and Claude Platform on AWS do not satisfy that same operating boundary.

Source: [Use Amazon Bedrock with interface VPC endpoints](https://docs.aws.amazon.com/bedrock/latest/userguide/vpc-interface-endpoints.html)

### Commercial and identity path

1. Must the purchase run through AWS, or can the team contract directly with Anthropic?
2. Does the application require AWS workload identity, or can it manage an Anthropic credential?
3. Are developer-local credentials prohibited, requiring a central gateway or workload role?

Commercial preference is not the same as the inference operator. Confirm both separately.

### Capability dependency

1. Which native feature would stop the project if it were unavailable?
2. Is an application-managed or AWS-hosted integration acceptable?
3. Does the team need Claude only, or multiple model providers behind one control plane?
4. Is the request about an API application, Claude Code, or an employee-facing Claude application?

For Claude Code, use the current
[feature availability table](https://code.claude.com/docs/en/feature-availability) rather than
assuming API feature parity.

### Production readiness

1. What region, geography, availability target, and data-retention policy apply?
2. What request and token rates must be supported, including bursts?
3. Who owns quotas, support, observability, rollback, and cost controls?
4. Has the required model and feature combination been verified in the intended region?

Model access and quotas are operational prerequisites, not feature preferences.

Source: [Access Amazon Bedrock foundation models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)

## Deterministic qualification rules

Treat these as starting rules, not a weighted score:

- **Bedrock is the leading path** when AWS-operated inference, Bedrock private endpoints, or a
  multi-model AWS control plane is a must-have.
- **Claude Platform on AWS is the leading path** when Anthropic operation is acceptable, the AWS
  commercial or identity relationship matters, and the project depends on Anthropic-native APIs
  exposed on that path.
- **Anthropic API is the leading path** when direct Anthropic administration and the broadest
  current Anthropic-native API surface matter more than AWS-specific controls.
- **Keep two paths alive** when the only difference is an unverified capability, region, quota, or
  commercial assumption. Test that assumption before recommending a migration.

## Evidence standard

For every material claim, provide:

- the public source URL
- the date it was checked
- whether the claim is documented, live-tested, or still unverified
- the exact path, region, model, and API mode when those details matter

Do not claim that one successful request proves production latency, reliability, cost, or support.
