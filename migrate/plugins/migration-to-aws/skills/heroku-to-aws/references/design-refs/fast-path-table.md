# Fast-Path Table — Add-On → AWS Service Mappings

## Description

This table provides deterministic mappings from Heroku add-ons to AWS service equivalents. The Design Engine uses this table during the design phase to automatically map known add-ons without requiring specialist evaluation. Add-ons matched here receive a confidence level of `"deterministic"`.

## Lookup Table

| Heroku Add-On | AWS Service(s) | Mapping Type | Notes |
|--------------|---------------|-------------|-------|
| Papertrail | CloudWatch Logs | Single | Log aggregation and search |
| SendGrid | Amazon SES | Single | Transactional and marketing email |
| Heroku Scheduler | EventBridge Scheduler | Single | Cron-style scheduled jobs |
| Memcachier | ElastiCache Memcached | Single | In-memory caching (Memcached protocol) |
| Bucketeer | S3 | Single | Object/file storage |
| CloudAMQP | Amazon MQ | Single | RabbitMQ-compatible message broker |
| Bonsai Elasticsearch | Amazon OpenSearch | Single | Full-text search and analytics |
| Scout APM | CloudWatch + X-Ray | Composite | Application performance monitoring + distributed tracing |
| Rollbar | CloudWatch | Single | Error tracking via structured logs |
| New Relic | CloudWatch + X-Ray | Composite | Full-stack observability + distributed tracing |
| Twilio | Amazon SNS (SMS) | Single | SMS messaging |
| Cloudinary | S3 + CloudFront | Composite | Media storage + CDN delivery |
| Sentry | CloudWatch | Single | Error tracking via structured logs |

## Interpretation Notes

- **Matching rule**: The add-on name from the inventory is matched against the "Heroku Add-On" column using **exact case-insensitive string comparison**. Partial matches (e.g., "Paper" matching "Papertrail") are NOT valid and must be treated as unmatched.
- **Confidence level**: All matches from this table produce a confidence level of `"deterministic"` in the design output.
- **Single mappings**: Map the source add-on to exactly one AWS service.
- **Composite mappings**: Map the source add-on to multiple AWS services that together replicate the source functionality. All listed services must appear in the design output as a single composite mapping with one `"deterministic"` confidence level assigned to the group.
- **Specialist gate**: Any add-on whose name does not exactly match (case-insensitive) an entry in this table is marked as `"Deferred — specialist engagement"` with no automated AWS mapping applied. The deferred record must include: add-on name, add-on plan, provider, reason for deferral, and a recommendation to engage the AWS account team.

## Error Handling

If a discovered add-on's name is not found in this table (no exact case-insensitive match), mark it as deferred:

> "Not found in Fast_Path_Table. Deferred to specialist engagement — engage AWS account team for replacement selection."
