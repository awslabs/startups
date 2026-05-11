# Contributing Guidelines

Thank you for your interest in contributing to `awslabs/startups`. This repository is owned and operated by the AWS Startups Build & Migrate team. It hosts developer plugins, MCPs, and tools for early-stage startup customers, distributed across marketplaces including Kiro, Claude, and Cursor.

Please read through this document before submitting issues or pull requests.

## First-Time Publishing

This section applies to contributors submitting a new plugin, MCP, or tool for the first time.

The Build & Migrate team controls what gets published. Contributors are responsible for securing all required approvals before submitting — we review the code and approvals, request changes if needed, and handle the first publish once everything meets the bar.

### Before You Submit

All code must reside in GitFarm (`code.amazon.com`) before it can be considered for publishing. We do not accept code from personal GitHub repos or local machines.

Secure the following before submitting:

- **PCSR approval** with Guardian sign-off (required for all artifacts)
- **Legal approval** (required for GenAI use cases or sensitive data handling)
- **AppSec review ticket** (if applicable based on risk profile)

### Intake Process

Submit a First-Time Publishing Request via the [intake form](https://us-east-1.quicksight.aws.amazon.com/sn/account/amazonbi/flows/view/245e35e6-3d72-42f5-8300-da099739d2f2?sso_login=true#). The form creates a SIM-TT ticket automatically — do not file tickets manually.

The intake form collects:

- Artifact name, purpose, and target startup customer persona
- Target marketplace(s): Kiro, Claude, Cursor, or other
- Dependencies (third-party libraries and AWS services used)
- A named **Artifact Owner** who will assume full ownership post-publish
- GitFarm URL where the code currently resides
- PCSR approval ticket link with Guardian sign-off
- Legal approval (if applicable)
- AppSec review ticket link (if applicable)

### SLAs

| Milestone | SLA |
|-----------|-----|
| Initial triage | Within 3 business days of submission |
| First publish | Within 2 weeks of a complete submission |
| Changes requested | SLA pauses; weekly status update from the team |

### Onboarding Checklist

The following must be complete before any new artifact is merged:

- [ ] `README.md` with all required sections (see [Per-Artifact Documentation](#per-artifact-documentation))
- [ ] `CHANGELOG.md` initialized
- [ ] Child CTI created under `AWS Startups / GH-Repo / [artifact-name]` with a linked Resolver Group
- [ ] PCSR approval ticket link provided with Guardian sign-off
- [ ] Legal approval provided (mandatory for GenAI use cases)
- [ ] AppSec review ticket link provided (if applicable)
- [ ] All automated security scans passing
- [ ] License compatibility confirmed for all dependencies
- [ ] Data handling summary reviewed
- [ ] Deployment validation in shared test environment completed
- [ ] Artifact Owner documented in `CODEOWNERS`

### Rejection Criteria

Submissions will be rejected if they are missing PCSR or Legal approvals, have no named Artifact Owner, fall outside the scope of AWS Startups developer content, or have dependencies with incompatible licenses. Written feedback with actionable next steps is provided via the SIM ticket.

---

## Post-Publish: Ongoing Contributions

Once an artifact is published, the designated **Artifact Owner** owns all future iterations. Changes go through the standard PR workflow — no repeated intake process.

Before sending a pull request:

1. Work against the latest source on the `main` branch.
2. Check existing open and recently merged pull requests to avoid duplication.
3. Open an issue to discuss any significant changes before investing time.

To send a pull request:

1. Create a feature branch: `feature/<artifact-name>/<short-description>`
2. Modify the source, focused on the specific change you are contributing.
3. Ensure local tests pass and automated scans are clean.
4. Commit using clear commit messages.
5. Submit the pull request and address any CI failures or reviewer feedback.

All PRs require at least one approval from a reviewer listed in `CODEOWNERS`. Security-sensitive changes — data handling, authentication, IAM permissions, external API calls — require a second review. Squash merges are preferred.

### Automated Guardrails

Every pull request runs:

- Automated security scans (ASH, Semgrep, Bandit, Grype)
- Secrets scanning (git-secrets, TruffleHog)
- Dependabot with enforced CVE SLAs (Critical: 7 days, High: 14 days, Medium: 30 days)
- License scanning on new dependencies
- Deployment validation in a shared test environment

---

## Per-Artifact Documentation

Each artifact directory must include:

**Required:**
- `README.md` — artifact name, purpose, target marketplace(s), installation and usage instructions, configuration options, data handling summary, known limitations, Artifact Owner contact
- `CHANGELOG.md` — version history with dates and descriptions of changes

**Recommended for complex artifacts:**
- `ARCHITECTURE.md` — high-level architecture, data flow, external dependencies
- `TESTING.md` — how to run tests and coverage expectations

---

## Maintenance

The Artifact Owner is responsible for ongoing maintenance post-publish: bug fixes, dependency updates, CVE remediation, runtime upgrades, and documentation updates.

**Stale content policy:**

| State | Trigger |
|-------|---------|
| Flagged for review | No commits for 6 months |
| Marked unmaintained | No response within 2 weeks of flag |
| Archived and unpublished | 30 days after marked unmaintained |

A new Artifact Owner can step forward to revive an archived artifact by completing the onboarding checklist.

---

## Reporting Bugs and Feature Requests

Use the GitHub issue tracker to report bugs or suggest features. Before filing, check existing open and recently closed issues to avoid duplicates. Include:

- A reproducible test case or series of steps
- The version of the artifact being used
- Any relevant modifications to your environment or configuration

---

## Code of Conduct

This project has adopted the [Amazon Open Source Code of Conduct](https://aws.github.io/code-of-conduct). See the [Code of Conduct FAQ](https://aws.github.io/code-of-conduct-faq) or contact opensource-codeofconduct@amazon.com with questions.

---

## Security Issue Notifications

If you discover a potential security issue, notify AWS/Amazon Security via the [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/). Do **not** create a public GitHub issue.

---

## Licensing

See the [LICENSE](LICENSE) file for this project's licensing. We will ask you to confirm the licensing of your contribution.
