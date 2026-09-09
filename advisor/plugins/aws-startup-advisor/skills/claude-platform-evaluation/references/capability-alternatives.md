# Capability Gaps and Alternatives

**Last reviewed:** 2026-09-09

Use this reference only for capabilities the user actually needs. A listed alternative can satisfy
an underlying requirement, but it is not automatically equivalent to a provider-native feature.

## Native Anthropic server tools

Anthropic documents server-side web search, Files API, and code execution for supported Claude
Platform paths. Check the current provider and model restrictions before making a recommendation.

- [Web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool)
- [Files API](https://platform.claude.com/docs/en/build-with-claude/files)
- [Code execution tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)

### Public web search

- **Native:** Use Anthropic web search where the selected path, model, region, and policy support it.
- **Integration alternative:** Put a licensed public-search API behind application tool code,
  Lambda, or an MCP-compatible gateway.
- **Not equivalent:** Search ranking, citations, data processing, billing, and operational ownership
  differ from Anthropic's server-side tool.
- **Do not substitute:** Amazon Kendra, OpenSearch, or Bedrock Knowledge Bases are enterprise
  retrieval options, not general public-web search engines.

### Durable files

- **Native:** Use the Files API when the selected path supports it and server-managed file reuse is
  the requirement.
- **AWS-native alternative:** Store durable objects in Amazon S3 with IAM and encryption controls,
  then pass supported document/image content through the application request path.
- **Not equivalent:** S3 provides object storage and governance, not Anthropic Files API lifecycle
  or request semantics.

Source: [Amazon S3 security best practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html)

### Code execution

- **Native:** Use Anthropic code execution where the selected path and model support it.
- **AWS-native alternative:** Use Amazon Bedrock AgentCore Code Interpreter for an isolated managed
  execution environment when its runtime and trust boundary fit the application.
- **Application alternative:** Run a separately secured sandbox owned by the application team.
- **Not equivalent:** Tool protocol, language/runtime behavior, file handling, audit evidence, and
  lifecycle differ.

Source: [AgentCore Code Interpreter](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/code-interpreter-tool.html)

## Agentic coding and employee access

Claude Code can use several provider paths, but features can differ by provider and authentication
mode. Always consult the current
[Claude Code feature availability table](https://code.claude.com/docs/en/feature-availability).

When centralized access, budgets, or Bedrock routing are required:

- [Claude Apps Gateway on AWS](https://code.claude.com/docs/en/claude-apps-gateway-on-aws) is a
  separate gateway layer for supported Claude applications.
- [LiteLLM with Claude Code and Bedrock](https://github.com/aws-samples/sample-claude-code-with-litellm-and-bedrock)
  is a customer-operated sample pattern for proxying and controls.

A gateway is not a fourth inference provider. Qualify its upstream provider separately and include
gateway operations, availability, identity, logs, and upgrades in the decision.

## Multi-model access

- **AWS-native:** Amazon Bedrock exposes multiple foundation-model providers through AWS service
  controls. Availability varies by model and region.
- **Gateway alternative:** A customer-operated gateway can normalize access to multiple providers.
- **Not equivalent:** A normalized API does not make models, safety behavior, tools, quotas, or
  response semantics interchangeable.

Source: [Amazon Bedrock supported foundation models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html)

## Administration and governance

- Anthropic API administration is documented through the
  [Claude Admin API](https://platform.claude.com/docs/en/manage-claude/admin-api).
- Amazon Bedrock uses AWS identity, service authorization, logging, and account/region controls.
- Claude Platform on AWS has its own documented administration and authentication surface; do not
  assume it is identical to either direct Anthropic administration or Bedrock IAM.

If a required administration endpoint or report is not documented for the selected path, mark it
**unverified** and test or confirm it before rollout.

## Alternative classification checklist

For every proposed alternative, state:

1. who operates it
2. where credentials and customer data flow
3. whether it changes the network or commercial boundary
4. who owns availability, quotas, upgrades, and incident response
5. which native semantics are lost or changed
