# Engine Configuration

With a committed GPU fleet, a model can run on several replicas, so one that fails after an image update is absorbed by the others while it is rolled back. A startup that chose one warm replica in `references/idle-floor.md` has no other replica: if a new image tag changes a memory default and the replica runs out of memory, the service is down. So defaults are not a configuration here. Pin the engine, and set every memory and concurrency setting explicitly in infrastructure as code from the budget in `references/fit-one-gpu.md`.

This file covers only what that budget needs from the engine. GPU node setup on EKS and ECS (accelerated AMIs, the NVIDIA device plugin, GPU support in the ECS agent, ECS Managed Instances) belongs to `Skill("aws-core:aws-containers")`, and EC2 AMIs, drivers and instance setup to `Skill("aws-core:aws-compute")`. Before tuning anything, confirm that the node advertises its GPU to the scheduler (`nvidia.com/gpu` on Kubernetes).

## Pin the engine

Versions checked for this file on 2026-10-05:

- vLLM v0.31.0 (released 2026-10-05). Docs for that version: [docs.vllm.ai/en/v0.31.0](https://docs.vllm.ai/en/v0.31.0/).
- SGLang v0.5.21 (released 2026-10-02). Docs at that tag: [server arguments](https://github.com/sgl-project/sglang/blob/v0.5.21/docs/docs/advanced_features/server_arguments.mdx).

Pin the container image by digest in Amazon ECR, record the engine version next to the model revision, and treat an engine upgrade like a model change: re-read the startup log lines in `references/fit-one-gpu.md`, re-run `references/benchmark-on-target.md`, and compare against the previous result before shifting traffic. Flag names and defaults below are from these versions; check them against the pinned version's docs before use.

## Map each fix to its setting

| Fix from `references/fit-one-gpu.md` | vLLM                                                       | SGLang                                                            | What it trades                                                                            |
| ------------------------------------ | ---------------------------------------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| GPU memory the engine claims         | `--gpu-memory-utilization` (fraction for the whole engine) | `--mem-fraction-static` (fraction for weights plus KV cache pool) | Higher means more KV cache and concurrency, less headroom for activations and CUDA graphs |
| 1. Bound context                     | `--max-model-len`                                          | `--context-length`                                                | Defaults come from the model config, often far above real traffic                         |
| 2. Bound concurrency                 | `--max-num-seqs`                                           | `--max-running-requests`                                          | Above the cap, requests queue instead of evicting others from the KV cache                |
| 3. Quantize the KV cache             | `--kv-cache-dtype`                                         | `--kv-cache-dtype`                                                | Needs an evaluation run                                                                   |
| 4. Quantize the weights              | `--quantization`                                           | `--quantization`                                                  | Supported formats depend on GPU architecture and engine version                           |
| 6. Tensor parallelism                | `--tensor-parallel-size`                                   | `--tp-size`                                                       | Leave at 1 unless step 6 was reached                                                      |
| Metrics for benchmark and scaling    | `/metrics` on the API server                               | `--enable-metrics`                                                | Needed by `references/benchmark-on-target.md`                                             |

Sources: vLLM [engine arguments](https://docs.vllm.ai/en/v0.31.0/configuration/engine_args/), [conserving memory](https://docs.vllm.ai/en/v0.31.0/configuration/conserving_memory/) and [production metrics](https://docs.vllm.ai/en/v0.31.0/usage/metrics/); SGLang [server arguments](https://github.com/sgl-project/sglang/blob/v0.5.21/docs/docs/advanced_features/server_arguments.mdx) and [hyperparameter tuning](https://github.com/sgl-project/sglang/blob/v0.5.21/docs/docs/advanced_features/hyperparameter_tuning.mdx).

Two defaults in these versions show why a default is not a setting: vLLM's `gpu_memory_utilization` defaults to 0.92, and its prefix caching is on by default (`vllm/config/cache.py` at v0.31.0). Set both explicitly, so the configuration does not change when the default does.

## Tune the one replica for latency

SGLang's tuning guide is written for throughput: it calls a queue of 100 to 2000 waiting requests healthy and aims for KV cache usage above 0.9. That suits offline work. An online replica with no second replica to spill to shows any sustained queue as time to first token, so tune it against the latency target in `references/benchmark-on-target.md`.
