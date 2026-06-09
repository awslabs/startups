# Messaging
## Service Selection Guide

| Requirement                             | Use                          |
|-----------------------------------------|------------------------------|
| Decouple producer from consumer, 1-to-1 | SQS                          |
| One message, multiple subscribers       | SNS + SQS (fan-out)          |
| Ordered, exactly-once processing        | SQS FIFO                     |
| Event routing based on content          | EventBridge                  |
| Cross-account/cross-region events       | EventBridge                  |
| Schema registry and discovery           | EventBridge                  |
| Simple mobile/email push notifications  | SNS                          |
| Replay past events                      | EventBridge Archive + Replay |

**Opinionated guidance:**
- Default to **EventBridge** for new event-driven architectures — it's more flexible than SNS for routing and filtering
- Use **SNS + SQS fan-out** for high-throughput workloads where EventBridge's throughput limits are a concern
- Use **SQS** directly when you just need a simple work queue with no fan-out

## Amazon SQS

### Standard vs FIFO

**Use Standard unless you need ordering or exactly-once.** The throughput difference is significant.

### Visibility Timeout
- Default: 30 seconds. Set it to at least 6x your average processing time.
- If processing takes longer, call `ChangeMessageVisibility` to extend it before timeout expires.
- If messages reappear in the queue, your visibility timeout is too short.

### Dead-Letter Queues (DLQs)
- **Always configure a DLQ.** Messages that fail processing silently retry forever without one.
- Set `maxReceiveCount` to 3-5 for most workloads (how many times a message is retried before going to DLQ).
- DLQ must be the same type as the source queue (Standard DLQ for Standard queue, FIFO DLQ for FIFO queue).
- Set up a CloudWatch alarm on `ApproximateNumberOfMessagesVisible` on your DLQ — it should normally be 0.
- Use DLQ redrive to move messages back to the source queue after fixing the bug.

### Polling Best Practices
- **Always use long polling** (`WaitTimeSeconds=20`). Short polling queries a subset of SQS servers and returns immediately — most responses are empty. At 4 polls/second that is ~345,600 empty API calls/day per consumer, each billed at the standard SQS rate. Long polling holds the connection open for up to 20 seconds and queries all servers, reducing empty responses by ~90% and cutting SQS API costs proportionally.
- Use batch operations: `ReceiveMessage` with `MaxNumberOfMessages=10` and `SendMessageBatch` for up to 10 messages.
- Delete messages immediately after successful processing.

## Amazon SNS

## Amazon EventBridge

### When to Choose EventBridge
- Content-based routing with complex rules
- Events from AWS services, SaaS integrations, or custom apps
- Schema discovery and registry for event contracts
- Cross-account or cross-region event delivery
- Event replay from archive

### Event Rules
- Match events with JSON patterns (event patterns)
- Up to 300 rules per event bus (soft limit)
- Each rule can have up to 5 targets
- Use input transformers to reshape events before delivery

```json
{
  "source": ["my.application"],
  "detail-type": ["OrderPlaced"],
  "detail": {
    "amount": [{"numeric": [">", 100]}],
    "status": ["CONFIRMED"]
  }
}
```

### EventBridge Pipes
- Point-to-point integration: source -> filter -> enrich -> target
- Sources: SQS, DynamoDB Streams, Kinesis, Kafka
- Reduces Lambda glue code for simple transformations
- Use filtering to process only relevant events from the source

### EventBridge Scheduler
- Cron and rate-based scheduling with one-time schedules
- Replaces CloudWatch Events scheduled rules
- Supports time zones and flexible time windows
- Can target any EventBridge target (Lambda, SQS, Step Functions, etc.)

### Throughput
- Default: 10,000 PutEvents per second per account per region (soft limit)
- For higher throughput, use custom event buses and request limit increases
- If you need >100K events/sec, consider SNS + SQS fan-out instead

## Common Patterns

### Saga / Choreography
```
Service A --event--> EventBridge --rule--> Service B --event--> EventBridge --rule--> Service C
```
Each service publishes events and reacts to events. Use DLQs on every consumer.

### Queue-Based Load Leveling
```
API Gateway --> SQS --> Lambda (batch processing)
```
SQS absorbs traffic spikes. Lambda processes at a controlled concurrency.

### Fan-Out with Filtering
```
Producer --> SNS Topic --> SQS Queue A (filter: premium)
                      --> SQS Queue B (filter: standard)
                      --> Lambda (filter: all, for analytics)
```


## Anti-Patterns

- **No DLQ on SQS queues.** Failed messages retry silently until they expire. You lose visibility into failures and potentially lose data.
- **Short polling SQS.** Short polling queries a subset of SQS servers and returns immediately — at 4 polls/second, that is ~345,600 empty API calls/day per consumer, each billed at standard SQS rate. Long polling (`WaitTimeSeconds=20`) queries all servers and holds the connection, reducing empty responses by ~90%.
- **Using SNS for point-to-point.** If there's only one subscriber, use SQS directly. SNS adds latency and cost for no benefit.
- **Giant messages in SQS/SNS.** Don't push large payloads through messaging. Store in S3, send a reference. The 256 KB limit exists for a reason.
- **Not designing for idempotency.** SQS Standard delivers at-least-once. SNS retries. EventBridge can replay. Every consumer must handle duplicate messages safely.
- **Tight coupling via message schemas.** If changing a message format breaks consumers, you've traded one form of coupling for another. Use EventBridge Schema Registry or version your message formats.
- **Using EventBridge for high-throughput streaming.** EventBridge is for event routing, not high-volume data streaming. Use Kinesis or MSK for >10K events/sec sustained.
- **Polling SQS from multiple consumers without proper visibility timeout.** If visibility timeout is too short, multiple consumers process the same message. Set timeout to 6x processing time.
- **No monitoring on DLQs.** A DLQ without an alarm is just a message graveyard. Alert on `ApproximateNumberOfMessagesVisible > 0`.
