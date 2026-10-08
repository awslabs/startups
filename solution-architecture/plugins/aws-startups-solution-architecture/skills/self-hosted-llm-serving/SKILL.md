---
name: self-hosted-llm-serving
description: "This skill should be used when a startup serves an open-weight or fine-tuned LLM online on an engine it runs itself, such as vLLM or SGLang on Amazon EKS, Amazon ECS or Amazon EC2, and the company has no committed GPU fleet, so every replica is new spend from a fixed cost ceiling and one idle GPU is a material share of it. Covers deciding from measured traffic whether self-hosting beats per-token or scale-to-zero managed options, fitting weights and KV cache on one GPU at the concurrency a latency target needs before paying for a second, serving several fine-tunes as adapters on one base model, and choosing between one warm replica and scale to zero priced against cold start. It should also be used when such an engine runs out of KV cache under load, sits idle most of the day, or costs more per token than the API it replaced. Not for running a model on SageMaker endpoints or Bedrock Custom Model Import, offline batch inference, training, or serving one model across several nodes."
license: Apache-2.0
metadata:
  audience: startup
---

# Self-Hosted LLM Serving

Serve an open-weight or fine-tuned LLM online on a self-managed engine (vLLM or SGLang) on Amazon EKS, Amazon ECS or Amazon EC2, for a company that has no committed GPU fleet and pays every replica from a fixed cost ceiling.

A company with a committed GPU fleet can add a model to capacity it already pays for, so an idle GPU costs it close to nothing. A small team in a large company without such a fleet runs the same arithmetic, but its idle GPU is a rounding error on the company bill. Here the first replica is new spend that runs whether or not traffic arrives, and one replica can be a material share of the ceiling. That idle GPU floor changes the defaults below.

## Decisions, and why the startup answer differs

| Decision             | With a committed GPU fleet                          | This skill                                                   | Reason                                                                                                                                 |
| -------------------- | --------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| Self-host or managed | Can add the model to capacity already paid for      | Stay managed until measured traffic crosses a break-even     | The floor is new monthly spend, so traffic has to cost more on a per-token or scale-to-zero option before the floor pays for itself    |
| Price used           | Priced at the committed rate                        | On-demand list price before credits                          | There is no commitment to amortize the GPU against, and the floor keeps running after credits run out                                  |
| Out of memory        | Can add GPUs already paid for                       | Bound, quantize or take a larger single GPU before a second  | In every G family with a multi-GPU size, the smallest one listed at least twice the smallest single-GPU size when checked (2026-10-05) |
| Several fine-tunes   | Can afford one endpoint each, for isolation         | Adapters on one base model                                   | Each extra endpoint adds a full GPU floor                                                                                              |
| Availability         | Can afford a second warm replica                    | One warm replica or scale to zero, chosen against cold start | A second warm replica doubles the largest line in the break-even                                                                       |
| Engine settings      | Other replicas absorb one that fails after an image | Every memory setting pinned in infrastructure as code        | With one replica, a default that changes on the next image pull takes the whole service down                                           |

## Scope

Apply this skill when all of these hold:

- The workload is online, interactive or near-interactive text generation from one LLM, optionally with fine-tuned adapters.
- The team runs the engine itself on EKS, ECS or EC2, or is deciding whether to.
- The hardware is NVIDIA GPUs, with one model server per node and tensor parallelism only within one instance. Extra replicas come from the platform's autoscaler.

Do not apply it to SageMaker endpoints, Bedrock Custom Model Import, offline batch work, training, embedding or diffusion models, or one model sharded across several nodes. Route those as listed under Upstream skills.

## Rule for numbers

Do not estimate a number in prose. Take GPU memory from the engine's startup log, throughput and latency from a benchmark on the target instance, prices from `Skill("aws-core:aws-billing-and-cost-management")`, and compute the break-even in a script under that skill's deterministic calculation rule. Without measured traffic, return the procedure and the list of missing measurements instead of a number.

## Decisions in order

### 1. Self-host or stay managed

Compare the idle GPU floor (the smallest replica that fits, running all month) against measured per-token spend and against the two managed options that scale to zero: Bedrock Custom Model Import and SageMaker endpoints with inference components. Output the break-even traffic number and the options ruled out by constraints; do not judge the company's stage. Read **`references/self-host-or-managed.md`**.

### 2. Fit one GPU first

Size weights plus KV cache at the measured context length and at the concurrency the latency target needs. If it does not fit, bound context or concurrency, quantize with a quality check, or move to a larger single GPU before adding a second. Read **`references/fit-one-gpu.md`**, then pin the result with **`references/engine-configuration.md`**.

### 3. Several fine-tunes: adapters on one base model

Serve LoRA adapters from one engine on one base model instead of one endpoint per fine-tune. Read **`references/multi-lora.md`**.

### 4. Idle floor: one warm replica or scale to zero

Choose between one warm replica, accepting no redundancy, and scale to zero, priced against measured cold-start time. Read **`references/idle-floor.md`**.

Measure before and after every decision with **`references/benchmark-on-target.md`**. Steps 1, 2 and 4 all consume its output.

## Required deliverables

- A break-even record: measured traffic profile, latency target, replica capacity from the benchmark, the on-demand list prices used with their lookup date, and the script that computed the result.
- A memory budget for the chosen GPU, taken from the engine's startup log at the configured context and concurrency.
- A pinned engine configuration: container image digest, engine version, model revision, and every memory and concurrency flag set explicitly in infrastructure as code.
- A benchmark result on the target instance with the engine configuration that will run in production.
- A written idle-floor decision: warm replica or scale to zero, the measured cold start, and what users see while a replica is unavailable.

## Upstream skills

Invoke these for the mechanics they own, which read the same for any company:

- **`Skill("aws-core:amazon-bedrock")`**: per-token model invocation, the comparison point in step 1.
- **`Skill("aws-core:aws-ai-ml")`**: Bedrock Custom Model Import and SageMaker endpoints, including sizing, adapter serving and benchmarking on SageMaker.
- **`Skill("aws-core:aws-billing-and-cost-management")`**: current prices and every cost calculation.
- **`Skill("aws-core:aws-containers")`**: EKS and ECS compute, GPU nodes, Karpenter, ECS Managed Instances, load balancing on EKS, and service scaling.
- **`Skill("aws-core:aws-compute")`**: EC2 GPU instance candidates, Auto Scaling groups, warm pools and Spot on EC2.
- **`Skill("aws-core:aws-storage")`**: staging model weights in Amazon S3.
- **`Skill("aws-core:aws-observability")`**: scraping engine metrics and alarming on them.
- **`Skill("aws-startups-solution-architecture:self-hosted-llm-batch-inference")`**: recurring offline inference where latency does not matter.

## Reference files

- **`references/self-host-or-managed.md`**: Read first, before choosing any GPU. Defines the constraints that rule out options, the traffic measurements, the managed comparators and the break-even calculation.
- **`references/fit-one-gpu.md`**: Read before choosing an instance type. Defines the memory budget, the startup log lines that confirm it, and the order of fixes before a second GPU.
- **`references/engine-configuration.md`**: Read before writing the deployment. Pins the engine and maps each fix from the memory budget to its vLLM and SGLang setting.
- **`references/multi-lora.md`**: Read when more than one fine-tune shares a base model. Defines when adapters replace endpoints, the adapter settings for each engine, and the memory they reserve.
- **`references/idle-floor.md`**: Read before setting minimum capacity. Defines the warm-replica and scale-to-zero options, how to measure and shorten cold start, Spot on a single replica, and idle node retention.
- **`references/benchmark-on-target.md`**: Read before step 1 and after every configuration change. Defines the workload, the concurrency sweep against a latency target, and the metrics that show saturation.

## Anti-patterns

- Self-hosting because per-token prices look high, without measuring traffic or computing the break-even against the idle floor.
- Pricing the break-even at a committed rate the company does not hold, or after credits.
- Starting the engine with default context length and memory settings on whatever GPU was available, then finding the KV cache limit under real concurrency.
- Answering an out-of-memory error with a multi-GPU instance before bounding context, bounding concurrency, quantizing or trying a larger single GPU.
- One endpoint per fine-tune of the same base model.
- Sizing from parameter count alone, or from a benchmark run on a different GPU, engine version or prompt distribution.
- Two warm replicas for redundancy that the ceiling cannot pay for, or one warm replica with nobody having decided what users see when it is down.
- Scale to zero without measuring cold start or deciding what happens to requests that arrive during it.
- A GPU node pool that keeps empty GPU nodes for hours or days after the last pod leaves.
- Engine flags left at the defaults of an unpinned image tag, so the next image pull changes memory behavior.
