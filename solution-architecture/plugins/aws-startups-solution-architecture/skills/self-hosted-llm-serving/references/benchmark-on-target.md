# Benchmark on the Target

A company with a committed GPU fleet can size from a rough benchmark and absorb the error in fleet headroom it already pays for. A startup cannot: the measured replica capacity sets the replica count in the break-even, the GPU choice and the idle-floor decision, so a capacity understated by one replica's worth adds a full GPU floor to the ceiling, and one overstated sends a replica more traffic than it can serve within the latency target, with no second replica behind it. The number to measure is how many concurrent requests one replica serves while still meeting the latency target.

Measure it on the exact instance type, engine version, engine flags and model revision that will run in production, with prompts shaped like real traffic. A benchmark from another GPU, another engine version or a public dataset with different lengths does not transfer.

For SageMaker endpoints, use the benchmark workflow in `Skill("aws-core:aws-ai-ml")` instead. This file covers self-managed engines on EKS, ECS or EC2.

## Build the workload from traffic

- Take input and output token lengths from production logs or the API bill being replaced, as distributions. Include the p99 request, because it decides the KV cache needed per request.
- Keep the real system prompt and chat template. A shared system prompt makes prefix caching help in production; a benchmark without it understates capacity, and a benchmark that repeats identical prompts overstates it.
- Write the latency target as numbers before running: time to first token and time per output token, each at a stated percentile.
- Remove personal or customer data from any prompt set copied out of production before it leaves the account.

## Tools

- vLLM: `vllm bench serve` against a running server ([benchmark CLI](https://docs.vllm.ai/en/v0.31.0/benchmarking/cli/)), with `--dataset-name custom` for a JSONL file of real prompts or `--dataset-name random` with lengths set from the measured distribution. `--goodput ttft:<ms> tpot:<ms>` counts only requests that met the latency target, which is the number this skill needs. Repeating it against the same server can reuse prompts left in the prefix cache and inflate throughput; vary `--seed`, restart the server, or use `vllm bench sweep serve`, which resets caches between runs.
- SGLang: `python3 -m sglang.bench_serving` with `--max-concurrency` and `--flush-cache` to clear the prefix cache after warm-up ([bench_serving](https://github.com/sgl-project/sglang/blob/v0.5.21/docs/docs/developer_guide/bench_serving.mdx)).

Run the client from a separate instance in the same Region and Availability Zone, so client CPU and network do not end up in the result. Pin the client tool version next to the engine version in the result file.

## Sweep concurrency against the latency target

1. Start the engine with the configuration from `references/engine-configuration.md` and record its startup log lines.
2. Run a short warm-up, then discard it.
3. Run the workload at increasing concurrency (for example 1, 2, 4, 8, 16, 32, then finer steps near the limit), long enough at each step for the latency percentiles to settle.
4. At each step record p50 and p99 time to first token, p50 and p99 time per output token, output tokens per second, goodput, and error count.
5. While it runs, scrape the engine's metrics and record the peak of each:
   - vLLM: `vllm:kv_cache_usage_perc`, `vllm:num_requests_waiting`, `vllm:num_preemptions` and `vllm:time_to_first_token_seconds` ([production metrics](https://docs.vllm.ai/en/v0.31.0/usage/metrics/)).
   - SGLang (with `--enable-metrics`): `sglang:token_usage`, `sglang:num_queue_reqs` and `sglang:time_to_first_token_seconds` ([production metrics](https://github.com/sgl-project/sglang/blob/v0.5.21/docs/docs/references/production_metrics.mdx)).

The replica capacity is the highest concurrency at which the p99 targets still hold and there are no preemptions. Report it with the output tokens per second at that point. Those two numbers go into the break-even script in `references/self-host-or-managed.md`.

Saturation looks like this in the metrics: KV cache usage near full, requests waiting above zero for sustained periods, preemptions counting up, and time to first token rising faster than concurrency. If preemptions appear below the concurrency the traffic needs, return to `references/fit-one-gpu.md`.

## Measure cold start in the same run

Stop the engine, remove the node or instance, and time a start from zero through the first successful request, broken into the parts listed in `references/idle-floor.md`. Repeat it several times; the slowest start is the one users meet.

## Record the result

Keep one result file per configuration with: instance type and Region, engine and client versions, image digest, model and adapter revisions, every engine flag, the startup log lines, the workload definition, the sweep table, the replica capacity, and the cold-start times. Re-run it after any engine upgrade, flag change, model change or instance change, and compare against the previous file before moving traffic.

## Scaling signal from the same metrics

The metrics that show saturation in the benchmark are the ones to scale on in production, and with a minimum of one replica or zero they decide when the second GPU floor starts billing. Requests waiting and KV cache usage react before latency does; GPU utilization reports the share of time any kernel was running, not how much KV cache is left. Set the threshold from the sweep, below the concurrency where the target broke, and wire it with `Skill("aws-core:aws-observability")` and the platform autoscaler in `Skill("aws-core:aws-containers")` or `Skill("aws-core:aws-compute")`.
