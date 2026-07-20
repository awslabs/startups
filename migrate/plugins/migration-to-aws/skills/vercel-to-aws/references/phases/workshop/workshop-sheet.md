---
_fragment: sheet
_of_phase: workshop
---

# Workshop — Assumption Sheet (Vercel)

> Confirm-first sheet. Not a full Clarify re-interview. Coupling / preflight /
> discovery stay frozen.

## Step 1: Read current knobs

From `clarify-answers.json` (+ defaults when `workshop` absent) and baseline
`recommendation.json` (for separability gating):

| Knob                   | Path                                      | Allowed / notes                                                  |
| ---------------------- | ----------------------------------------- | ---------------------------------------------------------------- |
| Traffic shape          | `Q1_traffic_shape.answer`                 | spiky / sustained / founder text (feeds Recommend A vs B)        |
| DB size                | `Q7_database_size.answer`                 | Only if key exists (Postgres peripheral)                         |
| Vercel spend           | `Q6_vercel_spend.answer`                  | Only if key exists AND no `discovery.usage_metrics.billing_data` |
| Target region          | `workshop.target_region`                  | AWS region; default `us-east-1`                                  |
| Balanced Multi-AZ      | `workshop.availability_multi_az_balanced` | boolean; default `false`                                         |
| CPU architecture       | `workshop.cpu_architecture`               | `arm64` (default, matches `graviton.md`) or `x86_64`             |
| Outcome override       | `workshop.outcome_override`               | `null` (engine) or `A` / `B` / `C` / `stay` — see C gating       |
| Backend shape (C only) | `workshop.backend_shape_override`         | `A-shaped` or `B-shaped`; required when override is `C`          |

Show current `recommendation.json.outcome` (and `separable` / `backend_shape`
when present) as read-only context on the sheet.

### Outcome C gating

- Offer **C** on the sheet **only if** the baseline (or current working-tree)
  `recommendation.json` has `separable === true`. If `separable` is absent or
  `false`, omit C from the override choices (list A / B / stay / null only).
- When the SA picks **C**, require `backend_shape_override` of `A-shaped` or
  `B-shaped` before Apply is valid. Do not invent a shape.

## Step 2: Present

Lead with:

> **What-if workshop** — discovery, coupling, and preflight are frozen. Edit
> assumptions to reprice. Generate/Terraform will be marked stale if already produced.
> Clarify answers you change keep a `workshop_note` with the original founder answer.

**Region / pricing honesty (always show under the table):**

> Region repricing needs the awspricing MCP for true regional rates. Without it,
> numbers stay based on the us-east-1 pricing cache (see any `region_note` on the
> estimate). Traffic/outcome/arch/Multi-AZ knobs reprice from design + cache.

Actions:

- **[A] Apply & reprice**
- **[B] Compare scenarios**
- **[C] Exit to Generate**
- **[D] Exit to full Clarify** (danger — resets Recommend→Estimate→Generate)

## Step 3: Validate (Apply only)

1. `workshop.target_region` is a non-empty AWS region code.
2. `workshop.cpu_architecture` is `arm64` or `x86_64`.
3. `workshop.outcome_override` is null or one of `A`|`B`|`C`|`stay`.
4. If `outcome_override == "C"`: baseline/current `separable === true` AND
   `backend_shape_override` is `A-shaped` or `B-shaped`.
5. Do not invent Q7/Q6 keys if they were skipped at Clarify.
6. On failure: re-present sheet; do not Recommend/Estimate.
