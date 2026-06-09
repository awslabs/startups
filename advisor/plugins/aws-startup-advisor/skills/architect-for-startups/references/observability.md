# Observability
## CloudWatch Metrics

## CloudWatch Logs

### Log Groups and Retention
- Set retention on every log group. The default is **never expire** — this gets expensive fast.
- Recommended: 30 days for dev, 90 days for production, archive to S3 for long-term

### Structured Logging
Always log in JSON format. This enables Logs Insights queries on fields.

## CloudWatch Alarms

### Alarm Best Practices
- Use **3 out of 5 datapoints** evaluation to avoid flapping on transient spikes
- Set `TreatMissingData` to `notBreaching` for low-traffic services (avoids false alarms when no data)
- Set `TreatMissingData` to `breaching` for critical health checks (missing data = something is down)
- Use composite alarms to create "alarm hierarchies": a top-level alarm that fires only when multiple sub-alarms are in ALARM state
- Always send alarms to SNS. Connect SNS to PagerDuty, Slack, or email.

### Anomaly Detection
- Trains on 2 weeks of data. Do not enable during a known-bad period.
- Adjust the bandwidth (number of standard deviations). Start with 2, widen if too noisy.
- Best for: request count, latency, error rate — metrics with daily/weekly patterns.

## CloudWatch Dashboards

### Dashboard Design
- One dashboard per service or domain (not one giant dashboard)
- Top row: key business metrics (request rate, error rate, latency p99)
- Second row: infrastructure health (CPU, memory, connections)
- Third row: dependencies (downstream API latency, queue depth)
- Use metric math to show rates and percentages, not raw counts
- Add text widgets to document what each section monitors and what to do when values are abnormal

### Automatic Dashboards
- CloudWatch provides automatic dashboards per service — start there before building custom
- ServiceLens provides an application-centric view combining metrics, logs, and traces

## X-Ray Tracing

### Instrumentation
- AWS SDK automatically instruments calls to AWS services
- Use X-Ray SDK or OpenTelemetry to instrument your application code
- Set sampling rules to control trace volume (default: 1 req/sec + 5% of additional)

### X-Ray Best Practices
- Add annotations for business-relevant fields (user ID, order ID) so you can filter traces
- Use groups to define filter expressions for specific trace sets
- Active tracing on API Gateway and Lambda captures the full request lifecycle
- X-Ray daemon runs as a sidecar in ECS or as a DaemonSet in EKS

## Contributor Insights

- Identifies top contributors to a metric (e.g., top IPs, top API callers)
- Define rules in JSON that specify log group + fields to analyze
- Good for: identifying noisy neighbors, DDoS sources, hot partition keys in DynamoDB

## Anti-Patterns

- **No log retention policy**: CloudWatch Logs default to never expire. Costs grow silently. Set retention on every log group.
- **Alarming on every metric**: Too many alarms leads to alert fatigue. Alarm on symptoms (error rate, latency), not causes (CPU). Use composite alarms to reduce noise.
- **Average-based latency alarms**: Averages hide tail latency. Use p99 or p95 for latency alarms.
- **Missing structured logging**: Unstructured logs cannot be queried efficiently with Logs Insights. Always log JSON.
- **No tracing in distributed systems**: Without X-Ray or OpenTelemetry, debugging cross-service issues requires correlating timestamps across log groups. Enable tracing.
- **Sampling rate of 100%**: Full tracing in production generates enormous data volume and cost. Use sampling — 1 req/sec + 5% is usually sufficient.
- **Not using Embedded Metric Format in Lambda**: EMF turns log lines into metrics with zero PutMetricData API calls. It's cheaper and simpler than the alternatives.
- **Dashboard without runbook links**: A dashboard that shows a problem without explaining what to do about it is only half useful. Add text widgets with runbook links.
- **Ignoring CloudWatch anomaly detection**: Static thresholds don't work for metrics with daily patterns. Use anomaly detection for request count and latency.
- **CloudWatch Agent not installed on EC2**: Without the agent, you only get basic metrics (CPU, network, disk I/O). Install the agent for memory utilization, disk space, and custom metrics.
