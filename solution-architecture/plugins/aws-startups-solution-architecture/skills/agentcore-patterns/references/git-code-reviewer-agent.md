# Running a judgment agent in your own CI path

Field notes from building an AgentCore agent that reviews pull requests for this
repository. Written as a reference rather than a skill, because most of the
underlying mechanics belong upstream: container and deploy mechanics are
`agents-deploy`, IAM scoping and session lifecycle are `agents-harden`, memory is
`agents-build`, all in `aws-agents`. Read those first. What follows is only the
decisions a small team has to make that those skills do not cover.

The startup constraint that shapes all of it: there is nobody to babysit this. A
reviewer that is wrong, slow, or noisy does not get tuned over a quarter by a
platform team. It gets ignored, and then it is worse than nothing because it
occupies the slot where review attention used to be.

## Decide what the agent is allowed to decide

The first design question is not the prompt. It is which findings may block a
merge.

| Finding kind                        | Blocks a merge      | Why                                                                                              |
| ----------------------------------- | ------------------- | ------------------------------------------------------------------------------------------------ |
| Deterministic and checkable in code | Yes                 | A count, a version tuple, a dangling path. If code can decide it, code should, and it is stable. |
| Model judgment, high agreement      | Yes                 | Two files giving contradictory instructions is reproducible across runs.                         |
| Model judgment, contested           | **No**              | Report it, quote it, let a human rule.                                                           |
| Anything a linter already covers    | Never report at all | Duplicate findings train people to skim past all of them.                                        |

The middle two are the ones that matter. Measure them before deciding, because
the answer is empirical rather than a matter of taste.

## Measure verdict stability before you let it gate anything

Run the reviewer against the same unchanged pull request several times and record
the verdict. This is the cheapest experiment available and it changes the design.

Doing this here produced, on four runs of one unchanged pull request:
`REQUEST_CHANGES`, `APPROVE`, `REQUEST_CHANGES`, `APPROVE`. The findings were
substantively defensible each time, and they sat at confidence 0.60 to 0.75
against a 0.6 reporting threshold, so they crossed it about half the time.

A verdict that changes on a rerun is worse than no verdict. A contributor who
re-runs CI, sees a different answer, and cannot tell which was right stops
believing any of the output. Note that the usual lever does not exist: newer
Claude models reject a `temperature` parameter outright, so determinism cannot be
bought that way.

Two fixes, in order of preference:

1. **Move the unstable axes out of the verdict.** Report them fully, block on
   none of them. Here that took a verdict that flipped twice in four runs to
   stable across three consecutive runs, with no loss of information.
2. **Self-consistency.** Run the judge N times, keep what appears in a majority.
   Directly targets variance, at N times the token cost, which is the tradeoff a
   small team is least able to absorb on every pull request.

## Surface the borderline instead of dropping it

A confidence threshold that silently discards everything below it throws away the
most useful output. The items a model is unsure about are exactly the ones worth a
human glance, and they are also the ones a threshold decides arbitrarily.

Three bands work better than one cutoff:

- Above the threshold: state it as a finding.
- In a band below it: surface it as borderline, quote the offending text, name
  what would settle it.
- Far below: drop it.

Widening from one cutoff to three bands here turned a review that reported
"no findings" into one that surfaced four specific, checkable suspicions at
confidence 0.35 to 0.45. Nothing about the model changed.

## Report a stance on every axis, including the clean ones

If the agent only speaks when it finds something, silence is ambiguous: a reviewer
cannot distinguish "checked, nothing there" from "never looked at that". Emit a
row per axis every run, with a one-line note even when clear. It costs a few
hundred tokens and it is the difference between output a reviewer trusts and
output they have to take on faith.

## Ground the model in facts computed by code

Anything countable should be counted in code and handed to the model as given
truth, not inferred by it. Skill counts, version tuples across manifest variants,
paths that no longer resolve. The model is then reasoning over verified numbers
instead of counting files in its head, which is where hallucinated specifics come
from.

The same principle applies to anything the judgment depends on. Checking "does
this duplicate an upstream capability" requires knowing what upstream actually
ships, so fetch the real inventory through the API rather than trusting model
memory of a repository. When that fetch fails, say so in the prompt and instruct
the model not to assert that a specific upstream component exists. An unavailable
inventory must read as "unknown", never as "upstream owns nothing".

## Do not let the reviewer read its own limitations as defects

Two failures here were the harness misleading the model, not the model being
wrong.

Truncating a diff mid-word produced a finding that a file "ends at `An AgentCore
runtime that j`". The file was fine; the cut was ours. Truncate on a line
boundary and label the truncation as a tool limit in the text the model sees.

The model also reported line numbers counted from the top of a diff hunk rather
than file lines, which would have anchored inline comments to unrelated code. A
prompt instruction helps, but arithmetic in a prompt is not reliable enough to
place a comment by: validate the line against the diff and drop it when it does
not match.

## Cost shape, and the one setting that matters

Runtime billing is per CPU-second and memory-second while a request is in flight,
so an idle reviewer costs nothing and the bill tracks pull-request volume. The
model tokens dominate, not the compute.

The setting worth attention is the idle session timeout. The default assumes a
conversational agent holding a session open; a reviewer runs for a minute and is
done. Setting it to minutes rather than the default is the difference between
paying for work and paying for a warm container waiting for nobody. See
`agents-harden` for session lifecycle mechanics.

One operational surprise worth knowing: a session id is pinned to a warm
container, so a stable id keeps serving the code that instance started with. A
fix can be deployed, the runtime can report a new version, the pushed image can
verifiably contain the fix, and invocations can still run the old code. Vary the
session id per invocation, and treat runtime version as insufficient evidence
that a change is live.

## Where the service depth comes from

- Container contract, deploy, versioning, rollback: `agents-deploy` in `aws-agents`.
- IAM scoping, inbound auth, secrets, session lifecycle, quotas: `agents-harden`.
- Memory, VPC, multi-agent, model selection: `agents-build`.
- Model choice and inference cost: `amazon-bedrock` and `aws-ai-ml` in `aws-core`.

## Anti-patterns

- **Letting a nondeterministic judge block a merge without measuring stability.**
  Run the same pull request repeatedly first. If the verdict moves, the judgment
  is advisory whether or not you label it that way.
- **Reporting what existing CI already reports.** Every duplicate finding lowers
  the odds anyone reads the novel one.
- **A single confidence cutoff.** The band just under it is the most useful
  output, and dropping it silently is the worst available handling.
- **Asserting a judgment the process reserves for a human.** If the contribution
  guide says reviewers decide, the agent quotes and defers. Claiming that
  authority is how the tool loses standing.
- **Trusting model-reported locations.** Validate line numbers against the diff
  before anchoring anything to them.
- **Treating a deployed version as proof the new code is running.** Warm
  containers outlive deploys.
