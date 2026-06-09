# Cloudfront
## Origin Types

### S3 Origins
- Use **Origin Access Control (OAC)** — not the legacy Origin Access Identity (OAI)
- OAC supports SSE-KMS, SSE-S3, and all S3 features. OAI does not.
- Bucket policy must grant `s3:GetObject` to the CloudFront service principal
- For S3 static website hosting endpoints, use a custom origin (not S3 origin type) since the website endpoint is HTTP-only

## Anti-Patterns

- **Using OAI instead of OAC**: OAI is legacy and doesn't support SSE-KMS. Always use Origin Access Control.
- **Caching dynamic content without a strategy**: Don't cache API responses unless you explicitly control TTLs and cache keys. Use CachingDisabled policy for APIs.
- **Invalidating as a deployment strategy**: Invalidations take time and cost money after 1,000 paths/month. Instead, use versioned file names (e.g., `app.abc123.js`) for cache busting.
- **Forwarding all headers/cookies/query strings**: This destroys cache hit ratio. Forward only what the origin needs. Use separate cache and origin request policies.
- **Not setting security response headers**: Always add HSTS, X-Content-Type-Options, X-Frame-Options via a response headers policy.
- **Edge-optimized API Gateway behind CloudFront**: Double-hop through two CloudFront distributions. Use regional API Gateway endpoint instead.
- **No WAF on public distributions**: CloudFront is the front door to your application. Protect it with WAF.
- **Wildcard invalidation on every deploy**: `/*` invalidates everything. Use path-specific invalidations or, better, versioned filenames.
- **Not compressing content**: Enable automatic compression in the cache behavior. CloudFront supports Gzip and Brotli.
- **Using self-signed certs with custom domains**: Use ACM certificates in us-east-1. They're free and auto-renew.
