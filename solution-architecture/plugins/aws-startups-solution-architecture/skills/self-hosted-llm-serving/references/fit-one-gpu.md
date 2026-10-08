# Fit One GPU First

A company with a committed GPU fleet can answer an out-of-memory error with more GPUs from capacity it already pays for. A startup pays for the second GPU from the ceiling, and on AWS list prices that is a large step. Price List GetProducts for Linux on-demand, shared tenancy, us-east-1 and eu-central-1, re-pulled 2026-10-05: in every current-generation G family that has a multi-GPU size, the smallest multi-GPU size lists at least twice as high as the family's smallest single-GPU size. The lowest ratio is exactly 2x, the Blackwell families g7 and g7e sit below 3x, and g4dn, g5, g6 and g6e sit above 5x, because those four families jump from one GPU straight to four.

So the order of fixes reverses: make the workload fit the smallest single GPU that holds it, and cross to a second GPU only after every single-GPU option below has failed, because the second GPU at least doubles the idle floor in `references/self-host-or-managed.md`. Re-check the ratio for the Region in scope with `Skill("aws-core:aws-billing-and-cost-management")` rather than trusting this date.

Get GPU instance candidates from `Skill("aws-core:aws-compute")`, and read GPU memory per GPU from EC2 `DescribeInstanceTypes` (`GpuInfo.Gpus[].MemoryInfo.SizeInMiB`). Keep one unit through the budget: the Price List shows decimal gigabytes, and engine logs use GiB.

## Size the budget from measurements

Online serving needs GPU memory for the weights, the KV cache for every request in flight, and the engine's own overhead. The KV cache grows with traffic, so a model that loads cleanly can still fail under real concurrency. Shortlist GPUs in a script from:

- Weights size from the staged model files at the chosen dtype or quantization. Parameter count times bytes per parameter is a first filter only.
- KV cache bytes per token from the model's `config.json`: 2 times layers times key-value heads times head dimension times bytes per element. Sliding-window, latent or hybrid attention use less; the engine log below is authoritative.
- Context per request from measured traffic: p99 input tokens plus p99 output tokens, not the model's maximum context.
- Concurrency from `references/benchmark-on-target.md`: the requests in flight that the latency target allows, not the largest batch the GPU can hold.

## Confirm with the engine

Start the engine on the candidate GPU with the settings from `references/engine-configuration.md`, then read the startup log before sending traffic, and again after every configuration change:

- vLLM logs `GPU KV cache size: <N> tokens` and `Maximum concurrency for <L> tokens per request: <X>x`. If X is below the concurrency the latency target needs at context L, the GPU does not fit this workload. vLLM refuses to start when one request at the configured maximum context does not fit, with an error that states the maximum model length the memory allows.
- SGLang logs `max_total_num_tokens`, `max_running_requests`, `context_len` and `available_gpu_mem` once the server is ready. Divide `max_total_num_tokens` by the measured context per request to get the concurrency it can hold.

Record the line in the deployment's change record. It is the measured memory budget the skill's deliverables ask for.

Sources: vLLM v0.31.0 `vllm/v1/core/kv_cache_utils.py`; SGLang v0.5.21 [hyperparameter tuning](https://github.com/sgl-project/sglang/blob/v0.5.21/docs/docs/advanced_features/hyperparameter_tuning.mdx).

## When it does not fit, in this order

1. Bound context. Set the maximum model length to the measured p99 request length plus a margin, not the model's advertised maximum. KV cache reserved for contexts nobody sends is memory taken from concurrency.
2. Bound concurrency. Cap requests in flight at the concurrency the latency target needs, so extra requests queue rather than evict others from the cache. vLLM documents that running short of KV cache causes preemption and recomputation, which hurts latency ([optimization guide](https://docs.vllm.ai/en/v0.31.0/configuration/optimization/)).
3. Quantize the KV cache. An 8-bit KV cache dtype roughly halves cache memory per token against 16-bit. Run the evaluation set before and after.
4. Quantize the weights. Check the pinned engine version's [quantization hardware table](https://docs.vllm.ai/en/v0.31.0/features/quantization/) against the GPU architecture (T4 is Turing, A10G is Ampere, L4 and L40S are Ada, g7 and g7e are Blackwell). The v0.31.0 table has no Blackwell column, so for g7 and g7e test the chosen method on the instance. Prefer a published quantized checkpoint of the same model, and accept it only if the evaluation set shows no regression the product cares about.
5. Take a larger single GPU. On 2026-10-05 in us-east-1, `DescribeInstanceTypes` returned 22888 MiB for the A10G (g5) and the L4 (g6), 45776 MiB for the L40S (g6e) and 98304 MiB for the RTX PRO Server 6000 (g7e), and g6e.xlarge (one L40S) listed at about a third of g5.12xlarge (four A10G) (Price List, derived ratio). Two traps on the way up: in g5, g6 and g6e, every size from xlarge to 16xlarge has the same single GPU, so a larger size buys vCPUs and host memory, not KV cache; and a large single-GPU size can list above the family's multi-GPU size (g4dn.16xlarge above g4dn.12xlarge), so compare per GPU memory, not per size name.
6. Only then, tensor parallelism across the GPUs of one instance. Record why each earlier step failed, because the decision at least doubles the floor. Serving one model across several nodes is out of scope.

## Leave headroom

Keep measured headroom between the configured memory fraction and the GPU total for activations, CUDA graphs and the runtime. SGLang's tuning guide suggests reserving 5 to 8 GB for activations as a rule of thumb, which is a large share of a 22888 MiB GPU; measure it on the target instead. A fleet absorbs a replica that runs out of memory at the first long request. With one warm replica, that restart is an outage, so size for slightly less concurrency rather than for the last gigabyte.
