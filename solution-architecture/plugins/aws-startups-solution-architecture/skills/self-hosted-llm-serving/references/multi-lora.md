# Several Fine-Tunes on One Base Model

A company with a committed GPU fleet can give each fine-tune its own endpoint, for separate ownership, separate deploys and isolation between fine-tunes, because the GPU under each one is capacity it already pays for. From a fixed ceiling, each of those endpoints carries its own idle GPU floor: three fine-tunes of one base model on three replicas is three times the floor from `references/self-host-or-managed.md`, usually for traffic that one replica could serve. So the default reverses. When the fine-tunes are LoRA adapters on the same base model, serve them from one engine: the base weights load once, and each request names the adapter it wants. Separate endpoints then need a reason stronger than tidiness.

## When adapters replace endpoints

Serve adapters from one engine when all of these hold:

- Every fine-tune is a LoRA adapter trained on the same base model revision, with the same tokenizer and chat template.
- The adapters' ranks are known, and the largest one fits the engine's rank limit without reserving much more memory than the others need.
- No contract or data rule requires one fine-tune's requests to run on hardware separate from another's. If one does, that fine-tune gets its own replica and its own line in the break-even.

Keep separate replicas when the fine-tunes use different base models, when one of them is a full fine-tune or a merged checkpoint, or when one adapter's traffic alone needs a full replica at the latency target.

Two managed paths own the adjacent cases, and `Skill("aws-core:aws-ai-ml")` covers both: SageMaker endpoints that serve several adapters, and Bedrock Custom Model Import, which imports merged weights, one model per fine-tune, and scales each to zero.

## Engine settings

vLLM v0.31.0 ([LoRA adapters](https://docs.vllm.ai/en/v0.31.0/features/lora/)):

- `--enable-lora` with `--lora-modules name=path` per adapter. A request selects an adapter by passing its name in the `model` field, and the base model stays addressable by its own name.
- `--max-loras`: adapters that can share one batch. Defaults to 1 in this version (`vllm/config/lora.py`), so with several adapters in live traffic, requests for different adapters do not batch together until it is raised.
- `--max-lora-rank`: defaults to 16. Set it to the largest rank among the adapters; the vLLM docs warn that a value far above it wastes memory.
- `--max-cpu-loras`: adapters kept in host memory, at least `--max-loras`.
- Loading adapters at runtime requires `VLLM_ALLOW_RUNTIME_LORA_UPDATING=True`, and the vLLM docs warn that it should not be used in production unless the environment is isolated and fully trusted. Prefer a fixed adapter list in the deployment, changed through the same pinned rollout as the engine.

SGLang v0.5.21 ([LoRA serving](https://github.com/sgl-project/sglang/blob/v0.5.21/docs/docs/advanced_features/lora.mdx)):

- `--lora-paths` lists adapters as `name=path` (this also enables LoRA).
- `--max-loras-per-batch`: adapters used by one batch, default 8. The docs note it affects the GPU memory reserved for multi-LoRA serving and should be lower when memory is scarce. Their example sets it to 2, one slot for the adapter and one for the base model.
- `--max-loaded-loras`: adapters held in host memory, at least `--max-loras-per-batch`.
- `--max-lora-rank` and `--lora-target-modules`: inferred from the listed adapters when not set; set them when adapters will be loaded after startup.

## Memory and capacity

Adapter slots reserve GPU memory that the KV cache would otherwise use. After enabling adapters:

1. Re-read the startup log lines in `references/fit-one-gpu.md` and re-check the fit against the concurrency the latency target needs. The KV cache size and maximum concurrency will be lower than without adapters.
2. Benchmark with the measured mix of adapter requests, not with base-model requests only. Set the batch adapter limit to the number of distinct adapters that are typically active at once, then confirm the latency target holds at that mix with `references/benchmark-on-target.md`.

If the adapters no longer fit next to the KV cache the traffic needs, lower the adapter rank limit or the per-batch adapter count before considering a second replica.

## Adapter lifecycle

- Store each adapter in Amazon S3 at an immutable revision, next to the base model revision it was trained on, and reject an adapter whose recorded base revision differs from the one being served.
- Route each product surface to its adapter by name in the request, so changing an adapter does not change the endpoint.
- Keep one evaluation set per adapter and run it on every engine or base-model upgrade, because an upgrade changes every adapter's behavior at once.
