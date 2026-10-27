# Self-Host or Stay Managed

A company with a committed GPU fleet can place the model on capacity it already pays for, so self-hosting costs it close to nothing extra. A startup has no fleet, so the first replica is new spend, billed every hour it runs whether or not traffic arrives. The question becomes a traffic threshold: how much measured traffic it takes before that idle GPU floor costs less than a per-token API or a managed option that scales to zero. The answer is a number computed from measurements.

The output of this step is one break-even traffic number per option, plus the list of options that constraints rule out before any cost is compared. It makes no judgment about whether the company is early or late, and it does not recommend self-hosting on the strength of a price list.

## Rule out options on constraints first

Record these before computing anything, because each one removes an option regardless of cost:

- Model architecture. Bedrock Custom Model Import accepts a fixed list of architectures (Mistral, Mixtral, Flan, Llama 2 to 3.3 and Mllama, GPTBigCode, Qwen2 to Qwen3 with limits on Qwen3 classes, GPT-OSS in US East (N. Virginia) only), text model weights under 200 GB, and a context length under 128K. It does not import embedding models, and the user guide asks that fine-tunes use transformers 4.51.3. Check the current list in the [Custom Model Import user guide](https://docs.aws.amazon.com/bedrock/latest/userguide/model-customization-import-model.html) rather than this summary.
- Region. Custom Model Import is listed in eu-central-1, us-east-1, us-east-2 and us-west-2 on the same page. If data must stay in another Region, the option is out.
- Infrastructure as code. The same page says Custom Model Import cannot be used with CloudFormation, while `references/engine-configuration.md` sets every serving flag in infrastructure as code. If the team requires every serving resource in CloudFormation or CDK, record that this option is managed outside it, or rule it out.
- Adapter format. Custom Model Import serves merged weights. If the fine-tunes must stay separate adapters on one base model, compare against `references/multi-lora.md` instead.
- Latency target. If a request must succeed within seconds of an idle period, any option that returns errors while it provisions from zero needs a fallback path, which `references/idle-floor.md` covers.
- Data handling terms that only a self-managed deployment satisfies. Record the requirement and its source; do not infer it.

## Measure the traffic

Collect from production logs or from the API bill being replaced, over at least one full weekly cycle:

- Input and output tokens per request, as distributions (median and p99), not averages.
- Requests per hour for every hour of the week, so idle hours are visible.
- Peak concurrent requests, and how long peaks last.
- The latency target the product needs: time to first token and time per output token at a stated percentile.
- Current monthly per-token spend, split into input and output tokens.

If the product has no traffic yet, stop here and report which measurements are missing. A break-even computed from a guessed traffic profile carries the guess's error into a fixed monthly cost.

## The four options and what each one costs at idle

| Option                                   | Cost when idle                                                         | Cost under load                                                                                  | Time to serve after idle                                     |
| ---------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------ |
| Per-token API on Amazon Bedrock          | None                                                                   | Input and output tokens at the model's price                                                     | None                                                         |
| Bedrock Custom Model Import              | None after it scales to zero (model storage still billed)              | Active model copies times Custom Model Units per copy, per minute of each active 5-minute window | Cold start on the first request after idle                   |
| SageMaker endpoint, inference components | None after scale-in to zero instances                                  | Instance hours while instances run                                                               | Several minutes to provision; invocations fail meanwhile     |
| Self-managed engine on EKS, ECS or EC2   | The warm replica floor, unless `references/idle-floor.md` chooses zero | Instance hours for every replica running                                                         | Node, image, weights and engine start when scaling from zero |

Sources for the managed rows, read 2026-10-05:

- Custom Model Import bills each model copy over 5-minute windows from its first successful invocation, and a window with at least one invocation is billed in full. Its cost is: model copies active in each window, times Custom Model Units per copy, times the price per Custom Model Unit per minute, times 5, summed over the active 5-minute windows. The source for that form is the worked example on [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/) (Custom Model Import tab), which bills one active window of a 2-unit copy as $0.1570 per minute (both units) times 5 minutes times 1 window, or $0.785. The formula on [Calculate the cost of running a custom model](https://docs.aws.amazon.com/bedrock/latest/userguide/import-model-calculate-cost.html) divides the window count by 60 where that example multiplies by 5, which prices the same window 300 times lower; use the pricing page form in the script. The number of units per copy is in `GetImportedModel` (`customModelUnitsPerModelCopy`) after import, so import the model before pricing it.
- Bedrock adds model copies when traffic exceeds what one copy can serve, and sets the concurrency one copy handles at import ([DeepSeek-R1 distilled Llama](https://aws.amazon.com/blogs/machine-learning/deploy-deepseek-r1-distilled-llama-models-with-amazon-bedrock-custom-model-import/)). `GetImportedModel` does not return that concurrency, so measure it: run the benchmark workload against the imported model and read the `ModelCopy` CloudWatch metric, which the user guide page names as the source for running copies.
- AWS blog posts on Custom Model Import state that it scales to zero after 5 minutes without invocations and that the first request afterwards can see cold-start latency of tens of seconds up to about a minute ([DeepSeek-R1 distilled Llama](https://aws.amazon.com/blogs/machine-learning/deploy-deepseek-r1-distilled-llama-models-with-amazon-bedrock-custom-model-import/), [Qwen](https://aws.amazon.com/blogs/machine-learning/deploy-qwen-models-with-amazon-bedrock-custom-model-import/)). Measure it for the actual model rather than relying on either figure.
- A SageMaker endpoint can scale to and from zero instances only if it hosts inference components, and provisioning from zero takes several minutes during which invocations return errors. See [Scale an endpoint to zero instances](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling-zero-instances.html).

Route the mechanics of the two managed options to `Skill("aws-core:aws-ai-ml")` and per-token invocation to `Skill("aws-core:amazon-bedrock")`. This file only uses their cost shape.

## Measure replica capacity before computing

A self-managed replica's capacity is not its peak throughput. It is the highest load at which the latency target still holds, measured on the target instance with the production engine configuration. Get it from `references/benchmark-on-target.md` as:

- Maximum concurrent requests per replica that meet the latency target at the measured token distribution.
- Output tokens per second per replica at that concurrency.

Without this number, the self-managed row has no cost under load, and the comparison cannot be made.

## Compute the break-even

Fetch every price with `Skill("aws-core:aws-billing-and-cost-management")` for the Region in scope, record the lookup date, and compute in a script. Do not do this arithmetic in prose.

Use on-demand list prices before credits for every option. With a committed fleet, a replica is priced at the committed rate; a startup holds no commitment to amortize a GPU against, and committing to one for a year or more locks in the floor this step exists to avoid. Credits lower the bill only until they run out, while the floor keeps running, so a break-even computed after credits is one the ceiling does not have to survive yet.

Inputs to the script:

- The hourly traffic profile from the measurements above.
- Per-token input and output prices for the per-token API.
- For Custom Model Import, if not ruled out: units per copy, the price per unit per minute, the maximum concurrency per copy from the load test above, the copies needed in each hour (the hour's peak concurrency divided by the concurrency per copy, rounded up), and the number of 5-minute windows in a month that contain at least one request, derived from the hourly profile at 5-minute resolution if available.
- For the self-managed engine: the hourly on-demand price of the chosen instance, replica capacity from the benchmark, the minimum replica count from the idle-floor decision, and fixed monthly costs that exist only for self-hosting (load balancer, cluster control plane if the cluster exists only for this model, NAT gateway, storage for weights).
- Operator hours per month to keep the engine patched, pinned and benchmarked, as a separate line the team fills in, and the same line for each managed option. The ceiling pays for those hours like any other cost.

What the script computes:

- Monthly cost of each option at the measured traffic, with Custom Model Import priced by the pricing page form above and its copy count taken per hour, not fixed at one.
- For each hour, the self-managed replicas needed: the larger of the minimum replica count and the hour's peak concurrency divided by replica capacity, rounded up.
- The traffic multiplier at which self-managed cost equals each managed option, holding the shape of the profile constant. That multiplier is the break-even number to report.

Report the break-even as "self-hosting costs less than option X once traffic is N times today's measured volume, at today's token mix and prices looked up on date D". If N is below 1, self-hosting already costs less; if it is far above 1, stay managed and re-run the script when traffic changes.

## When the answer is to stay managed

Stay on the managed option and keep the measurements when any of these hold:

- Measured traffic sits below the break-even.
- The traffic profile has long idle hours and the self-managed option needs a warm replica to meet the latency target.
- Nobody on the team can own engine upgrades and benchmarks; the operator-hours line is then a cost with no one to pay it.

Re-run the script when monthly per-token spend grows materially, when a fine-tune is added, or when prices change. The decision is reversible in both directions as long as the prompt contract and evaluation set stay independent of the serving option.
