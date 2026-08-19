# An agent that reviews pull requests

End-to-end wiring for an AgentCore agent that reviews pull requests: how it
authenticates to GitHub, what it remembers between reviews, why the obvious CI
trigger cannot reach it, and the judgment design that decides whether anyone
trusts its output.

Building and deploying the agent is upstream: `agents-build` and `agents-deploy`
in `aws-agents`. Nothing here restates them.

## Authentication: the identity decides what the agent may do

The choice is not "token or App" on convenience grounds. GitHub refuses `APPROVE`
and `REQUEST_CHANGES` when the credential's owner authored the pull request:

```text
422 Unprocessable Entity
Review Can not approve your own pull request
```

A personal access token therefore cannot record a verdict on your own work, only
a comment. A GitHub App is a distinct identity, so its verdicts stand and the
review is attributed to the bot rather than to a person.

| Credential              | Reads a public repo  | Posts a verdict on your own PR | Rate limit                  |
| ----------------------- | -------------------- | ------------------------------ | --------------------------- |
| No credential           | yes                  | no                             | 60/hour per IP              |
| Personal access token   | yes                  | downgrades to a comment        | 5,000/hour                  |
| GitHub App installation | yes, where installed | yes                            | 5,000/hour per installation |

Practical consequences for a small team:

- **An organization owner must install an App.** Repository write access is not
  sufficient, and a private App can only be installed on the account that owns
  it, so an App intended for an organization must be public. Expect to request
  installation and wait.
- **Enterprise policy can reject a token outright**, independently of its scopes.
  A fine-grained token whose lifetime exceeds a policy limit fails with
  `403 Resource not accessible by personal access token` even though the same
  token works elsewhere. Read the message rather than adding scopes.
- **Degrade rather than fail.** Resolve credentials in order: App, then token,
  then unauthenticated. One App is never installed everywhere the agent is asked
  to review, and a missing installation is an expected condition. Enabling App
  auth without that fallback broke review of a repository where the App was not
  installed, because the installation lookup threw and killed the run.
- Store the App private key in Secrets Manager and read it with the runtime's
  execution role. GitHub issues PKCS#1; WebCrypto needs PKCS#8, so convert once
  with `openssl pkcs8 -topk8 -nocrypt` and store the result.

## Never check out the pull request

Read changed files through the REST API as data. Do not clone the branch, do not
run anything from the diff. A reviewer that executes untrusted contributor code
is a supply-chain hole with a friendly name, and reading via API is also what
makes the same agent safe to point at forks later.

## The CI trigger, and why the obvious one fails

On a public repository, pull requests arrive from forks, and **a `pull_request`
workflow triggered by a fork receives no secrets and no OIDC token.** It cannot
assume a role, so it cannot invoke the runtime. This is the wiring that silently
does not fire.

| Trigger               | Has credentials on fork PRs | Note                                                                             |
| --------------------- | --------------------------- | -------------------------------------------------------------------------------- |
| `pull_request`        | no                          | Works only for same-repository branches                                          |
| `pull_request_target` | yes                         | Runs in the base repo context. Checking out the fork head here leaks credentials |
| `workflow_run`        | yes                         | Base-repo context, reads the PR through the API, never checks out fork code      |

`workflow_run` after the existing build is the safe default. Because the agent
already reads through the API rather than checking anything out, moving between
triggers is a workflow-file change rather than an agent rewrite.

Two invocation details that fail with unhelpful errors: the session id has a
minimum length (pad short ids), and the payload content type must be set
explicitly.

## Memory: what is worth remembering

Use `actorId` for the repository and `sessionId` for the pull request, so
decisions accumulate per repository and each review's turns stay grouped.
Persist a one-line outcome per review; retrieve prior decisions before judging so
the agent can say "this pattern was already rejected" instead of re-litigating.

Treat memory as an enhancement, never a dependency. A cold or failed retrieval
must not fail the review.

## The judgment design that decides whether anyone trusts it

The startup constraint bites hardest here. Nobody will tune this over a quarter.
A reviewer that is noisy or inconsistent gets ignored, and then it is worse than
nothing, because it occupies the slot where review attention used to be.

**Report nothing your existing CI already reports.** Formatting, schema
validation, secret scanning, and dependency CVEs are already covered. Every
duplicate finding lowers the odds anyone reads the novel one. Name those tools in
the prompt as out of scope.

**Measure verdict stability before letting the agent gate anything.** Run it
against the same unchanged pull request several times and record the verdict. In one measured
case four runs produced `REQUEST_CHANGES`, `APPROVE`, `REQUEST_CHANGES`, `APPROVE`: the
findings were defensible each time but sat at confidence 0.60 to 0.75 against a
0.6 threshold, so they crossed it about half the time. A verdict that changes on a
rerun is worse than no verdict. Note that the usual lever is gone, since newer
Claude models reject a `temperature` parameter outright.

The fix that cost nothing was to move the unstable categories out of the verdict:
report them fully, block on none of them. That took a verdict flipping twice in
four runs to stable across three, with no information lost. Self-consistency
voting across N runs also works and costs N times the tokens.

**Surface the borderline rather than dropping it.** A single threshold discards
exactly the arguable cases a human most wants to see. Three bands work better:
state findings above the threshold, surface the band below it as borderline with
the offending text quoted, drop the rest. In the same case, widening to three bands turned a
review that reported "no findings" into one that surfaced four specific,
checkable suspicions at confidence 0.35 to 0.45, with no model change.

**Report a stance on every axis, including the clean ones.** If the agent speaks
only when it finds something, silence cannot be distinguished from never having
looked.

**Compute facts in code and hand them to the model as given truth.** Counts,
version tuples, paths that no longer resolve. The model then reasons over verified
numbers instead of counting in its head, which is where invented specifics come
from. When a lookup the judgment depends on fails, say so in the prompt and
forbid asserting that the thing exists: unavailable must read as "unknown", never
as "absent".

## Do not let the agent read your harness limits as defects

Two findings here were the harness misleading the model.

Truncating a long diff mid-word produced a finding that a file "ends at
`An AgentCore runtime that j`". The file was fine; the cut was ours. Truncate on a
line boundary and label the truncation as a tool limit in the text the model sees.

The model also reported line numbers counted from the top of a diff hunk rather
than file lines, which would have anchored inline comments to unrelated code. A
hunk header `@@ -a,b +c,d @@` states the new-side start; prompt instructions help,
but arithmetic in a prompt is not reliable enough to place a comment by. Validate
the line against the diff and drop it when it does not match. Posting a comment
against a line outside the diff also rejects the entire review, so anchor only
what you have verified and put the rest in the summary.

## Operational notes

- **A session id is pinned to a warm container.** A stable id keeps serving the
  code that instance started with. A fix can be deployed, the runtime can report a
  new version, the pushed image can verifiably contain the fix, and invocations can
  still run the old code. Vary the session id per invocation, and treat runtime
  version as insufficient evidence that a change is live.
- **Set the idle session timeout deliberately.** The default suits a
  conversational agent holding a session open. A reviewer runs for a minute, so
  minutes rather than hours is the difference between paying for work and paying
  for a warm container waiting for nobody.
- **Public network mode is required if the agent calls GitHub.** VPC mode has no
  egress without a NAT gateway, which is a standing cost for a workload whose only
  outbound calls are an API and a model.
- Cost tracks pull-request volume, and model tokens dominate the per-second
  compute.

## Anti-patterns

- **Checking out the pull request branch.** Read through the API. Cloning
  contributor code into a credentialed runtime is the whole vulnerability.
- **`pull_request_target` with a fork-head checkout.** The credentials it grants
  are exactly what the checkout exposes.
- **Letting a nondeterministic judge block a merge without measuring stability.**
  If the verdict moves across runs, the judgment is advisory whether you label it
  that way or not.
- **Reporting what existing CI reports.** Duplicates train people to skim past
  everything, including the finding that mattered.
- **A single confidence cutoff.** The band just below it is the most useful
  output; dropping it silently is the worst available handling.
- **Asserting a judgment your process reserves for a human.** If the contribution
  guide says reviewers decide, quote and defer. Claiming that authority is how the
  tool loses standing.
- **Treating a deployed version as proof the new code is running.** Warm
  containers outlive deploys.
