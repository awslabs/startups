# API Gateway

## Decision Framework: REST API vs HTTP API

**Opinionated recommendation**:
- **Default to HTTP API**. It is cheaper, faster, and simpler for 80% of use cases.
- **Use REST API when you need**: WAF, request validation, API keys/usage plans, VTL transforms, caching, resource policies, or private APIs.
- **Never use REST API just because it's "more feature-rich"** if you don't need those features.

## Authorizer Patterns

Choose the right authorizer based on your use case:

| Scenario                                 | Recommended Authorizer                                     |
|------------------------------------------|------------------------------------------------------------|
| Web/mobile app with Cognito              | JWT authorizer (HTTP API) or Cognito authorizer (REST API) |
| Third-party OIDC (Auth0, Okta)           | JWT authorizer (HTTP API)                                  |
| Custom token format or multi-header auth | Lambda authorizer (REQUEST type)                           |
| Service-to-service (internal)            | IAM authorization with SigV4                               |

**Opinionated**: Cache authorizer results (300s is a reasonable default) — without caching, every API call invokes your authorizer Lambda, which adds latency (50-200ms) and cost (you pay per invocation). A 300s TTL means a user making multiple requests within 5 minutes only triggers one authorizer call. Adjust down for sensitive operations. Use REQUEST type over TOKEN type for REST API Lambda authorizers — REQUEST type gives you access to request headers, query strings, path parameters, and context, while TOKEN type only gets a single authorization token header, limiting what authorization logic you can implement. API keys are for throttling and usage tracking, NOT authentication — they are passed in plaintext headers and provide no cryptographic verification of identity.

## Throttling and Rate Limiting

### Account-Level Defaults
- **10,000 requests/second** across all APIs in a region (soft limit, can increase)
- **5,000 burst** across all APIs

**Opinionated**: API keys are for throttling and tracking, NOT authentication. They are sent in headers and easily leaked. Always combine with a real authorizer.

## Custom Domains

**Requirements**: ACM certificate must be in **us-east-1** for edge-optimized endpoints. For regional endpoints, the cert must be in the same region as the API.

## Stages and Deployment

**Opinionated**: Use separate AWS accounts (not just stages) for prod vs non-prod. Stage variables are useful but don't replace proper environment isolation.

## Request/Response Transforms (REST API)

**Opinionated**: VTL is painful to debug and maintain. For complex transforms, use a Lambda integration instead. Reserve VTL for simple cases like adding request context or status code mapping.

## WebSocket APIs

**Key design decisions for WebSocket**:
- Store connection IDs in DynamoDB (not in-memory)
- Use `$connect` route for authentication
- Set idle timeout (default 10 min, max 2 hours)
- Max message size is 128 KB (frames up to 32 KB)
- Use API Gateway management API to push messages from backend

## CORS Configuration

- **HTTP API**: Built-in CORS support via `cors-configuration`. One command configures everything.
- **REST API**: Requires manual OPTIONS method with mock integration on each resource, plus CORS headers on all integration responses. Use SAM/CDK to automate this -- doing it manually via CLI is error-prone.

**Key rules**: Never use wildcard origins in production. If using credentials, you must specify exact origins. For REST API with Lambda proxy integration, return CORS headers from your Lambda function, not from API Gateway.

## Anti-Patterns

1. **Using REST API when HTTP API suffices**: Paying 3.5x more for features you don't use. Audit your feature requirements.
2. **API keys as sole authentication**: API keys are identifiers, not authenticators. Always pair with IAM, Cognito, or Lambda authorizers.
3. **No throttling on public APIs**: Without throttling, a single client can exhaust your account-level limit, affecting all APIs.
4. **Deploying without stage-specific settings**: Each stage should have its own logging, throttling, and Lambda alias configuration.
5. **Large payloads through API Gateway**: Payload limit is 10 MB. For file uploads, use pre-signed S3 URLs instead.
6. **Ignoring the 29-second timeout**: API Gateway has a hard 29-second integration timeout. Design for async patterns (return 202, poll/webhook) for long-running operations.
7. **Not enabling CloudWatch Logs**: Without execution logs, you cannot debug 5xx errors. Enable at minimum ERROR-level logging.
8. **Wildcard CORS in production**: `AllowOrigins: *` in production exposes your API to any origin. Specify exact allowed origins.
9. **Complex VTL mapping templates**: VTL is hard to test, debug, and maintain. If your transform is more than 10 lines, move it to Lambda.
10. **Not using a custom domain**: The default `execute-api` URL changes on redeployment (REST API). Custom domains provide stable URLs and allow API migration without client changes.

## Cost Optimization

- HTTP API is 70% cheaper than REST API for the same traffic
- Enable REST API caching to reduce Lambda invocations (but adds ~$0.02/hour per GB)
- Use Lambda authorizer caching to avoid re-executing authorizer on every request
- For high-traffic APIs, consider CloudFront in front of API Gateway for additional caching
- Monitor 4xx errors -- wasted invocations from bad clients still cost money
