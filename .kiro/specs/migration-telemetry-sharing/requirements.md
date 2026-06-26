# Requirements Document

## Introduction

The GCP-to-AWS migration plugin currently offers feedback checkpoints after the Discover phase and after the Estimate phase (5 optional survey questions plus an anonymized trace). However, there is no telemetry on whether users complete the full 6-phase pipeline, and no mechanism to connect users with AWS migration partners or AWS support after receiving their migration results. This feature adds a "share your plan" mechanism that encodes the user's migration profile into a URL fragment, allowing the AWS Startups landing page to decode it client-side, render a summary, and match the user with relevant migration partners. The feature also restructures existing feedback checkpoints: removing the premature post-Discover checkpoint, combining feedback with the share link after Estimate, and presenting only the share link after Generate.

## Glossary

- **Plugin**: The GCP-to-AWS migration skill executed by the agent, defined in `SKILL.md` and its reference files.
- **Pipeline**: The 6-phase migration process: Discover → Clarify → Design → Estimate → Generate → Feedback.
- **Share_Link**: A URL containing a Base64-encoded, compressed JSON payload in the URL fragment (after the `#` character), pointing to the AWS Startups landing page.
- **Landing_Page**: The external web page at `https://aws.amazon.com/startups/migrate/connect` that decodes the Share_Link payload client-side and presents partner matching. Out of scope for plugin implementation.
- **Payload**: The compressed, Base64-encoded JSON object embedded in the Share_Link URL fragment containing the user's migration profile data.
- **Migration_Profile**: The collection of Clarify answers, cost estimates, recommendation path, detected services, and workload metadata that forms the shareable data.
- **Consent_Disclosure**: The explicit plain-language statement shown to the user before the Share_Link, enumerating exactly what data is included and excluded.
- **Feedback_Questions**: The existing 5 optional survey questions presented via the Pulse survey form.
- **Partner_Routing**: The process by which the Landing_Page filters migration partners based on workload type and spend threshold. Performed entirely by the Landing_Page, not the Plugin.
- **URL_Fragment**: The portion of a URL after the `#` character, which is never sent to the server and is accessible only client-side.
- **Payload_Encoder**: The component within the Plugin responsible for assembling, compressing, and Base64-encoding the Migration_Profile into a URL fragment.
- **Spend_Band**: A categorical range representing the user's monthly cloud spend (e.g., "under-10k", "10k-50k", "50k-100k", "over-100k").

## Requirements

### Requirement 1: Remove Post-Discover Feedback Checkpoint

**User Story:** As a migration user, I want to avoid being interrupted for feedback before I have meaningful results, so that the feedback I provide is informed and the flow feels efficient.

#### Acceptance Criteria

1. WHEN the Discover phase completes, THE Plugin SHALL proceed directly to the Clarify phase without presenting any feedback offer or survey prompt.
2. THE Plugin SHALL remove the "After Discover" feedback checkpoint logic from the state machine in SKILL.md.
3. WHEN the Plugin reads a `.phase-status.json` where `phases.feedback` is `"pending"` and `phases.discover` is `"completed"`, THE Plugin SHALL NOT present a feedback prompt until after the Estimate phase completes.

### Requirement 2: Combined Feedback and Share Link After Estimate

**User Story:** As a migration user who has received my cost estimate, I want to see feedback questions and a share link together in one prompt, so that I can provide feedback and connect with partners in a single interaction.

#### Acceptance Criteria

1. WHEN the Estimate phase completes and `phases.feedback` is `"pending"`, THE Plugin SHALL present the 5 Feedback_Questions combined with a Share_Link in a single output block.
2. THE Plugin SHALL present the Share_Link as a clearly labeled clickable link with the text "Share my plan & see matched partners".
3. WHEN the user declines both feedback and sharing after Estimate, THE Plugin SHALL set `phases.feedback` to `"completed"` and proceed to the Generate phase.
4. WHEN the user chooses to share, THE Plugin SHALL generate the Share_Link and display it to the user before proceeding to the Generate phase.
5. THE Plugin SHALL present the combined feedback and share prompt as three options: [A] Send feedback & share plan, [B] Send feedback only, [C] No thanks, continue to Generate.

### Requirement 3: Share Link After Generate

**User Story:** As a migration user who has completed the full pipeline, I want one final opportunity to share my completed plan with AWS partners, so that I can get migration support with all artifacts available.

#### Acceptance Criteria

1. WHEN the Generate phase completes, THE Plugin SHALL present a Share_Link with the text "Share completed plan".
2. THE Plugin SHALL NOT re-present the 5 Feedback_Questions after the Generate phase.
3. WHEN the user declines the share link after Generate, THE Plugin SHALL proceed to mark the migration as complete.
4. THE Plugin SHALL present the post-Generate share prompt as two options: [A] Share completed plan, [B] No thanks, finish.

### Requirement 4: Payload Assembly

**User Story:** As a migration user, I want my migration profile accurately encoded in the share link, so that the landing page can display my details and match me with appropriate partners.

#### Acceptance Criteria

1. THE Payload_Encoder SHALL include all Clarify Q&A answers from `preferences.json`, including both user-provided and auto-inferred answers.
2. THE Payload_Encoder SHALL include the recommendation path value (one of: `migrate_optimized`, `migrate_phased`, `stay`) from the active estimation artifact.
3. THE Payload_Encoder SHALL include the recommendation rationale text from the active estimation artifact.
4. THE Payload_Encoder SHALL include the cost summary containing current GCP monthly spend, projected AWS monthly spend, and the delta between them.
5. THE Payload_Encoder SHALL include the list of detected GCP service types from `gcp-resource-inventory.json`.
6. THE Payload_Encoder SHALL include the workload types detected (one or more of: `ai`, `infra`, `billing-only`).
7. THE Payload_Encoder SHALL include the monthly Spend_Band derived from the billing profile or estimation data.
8. THE Payload_Encoder SHALL include GCP resource names (e.g., "google_sql_database_instance named prod-db") from the resource inventory.

### Requirement 5: Payload Encoding and URL Construction

**User Story:** As a migration user, I want the share link to be a self-contained URL that works in any environment, so that I can click it from any IDE or terminal.

#### Acceptance Criteria

1. THE Payload_Encoder SHALL serialize the Migration_Profile as JSON, compress it, and encode it as URL-safe Base64.
2. THE Payload_Encoder SHALL construct the Share_Link as `https://aws.amazon.com/startups/migrate/connect#<base64payload>`.
3. THE Payload_Encoder SHALL produce a Payload that fits within 8,192 characters when Base64-encoded, to remain within common URL length limits.
4. IF the compressed Payload exceeds 8,192 Base64 characters, THEN THE Payload_Encoder SHALL truncate the Clarify answers by removing auto-inferred answers first, then removing lowest-priority user answers, until the Payload fits within the limit.
5. THE Payload_Encoder SHALL use the URL fragment (after `#`) so that payload data is never transmitted to a server during link navigation.

### Requirement 6: Consent Disclosure

**User Story:** As a migration user, I want to know exactly what data is being shared before I click the link, so that I can make an informed decision about sharing.

#### Acceptance Criteria

1. WHEN presenting a Share_Link, THE Plugin SHALL display a Consent_Disclosure immediately before the link.
2. THE Consent_Disclosure SHALL state what data IS included: "This sends your Clarify answers, estimated costs, recommendation path, detected services, and workload types."
3. THE Consent_Disclosure SHALL state what data is NOT included: "No source code, file paths to your local machine, or credentials are shared."
4. THE Consent_Disclosure SHALL be presented as plain text readable in any terminal or IDE output.
5. THE Plugin SHALL NOT transmit any payload data to a remote server; the Share_Link uses the URL_Fragment which remains client-side.

### Requirement 7: Payload Data Exclusions

**User Story:** As a migration user, I want assurance that sensitive data from my local environment is excluded from the share link, so that my security posture is not compromised.

#### Acceptance Criteria

1. THE Payload_Encoder SHALL NOT include source code file contents in the Payload.
2. THE Payload_Encoder SHALL NOT include local file system paths in the Payload.
3. THE Payload_Encoder SHALL NOT include AWS credentials or access keys in the Payload.
4. THE Payload_Encoder SHALL NOT include `.tfstate` file contents in the Payload.
5. THE Payload_Encoder SHALL NOT include environment variable secrets in the Payload.
6. THE Payload_Encoder SHALL NOT include raw billing CSV row data in the Payload.
7. IF any field in `preferences.json` contains a value matching a known secret pattern (AWS key format, private key headers, connection strings with passwords), THEN THE Payload_Encoder SHALL redact that field value before encoding.

### Requirement 8: Payload Schema Versioning

**User Story:** As the landing page maintainer, I want the payload to include a schema version, so that the decoder can handle payloads from different plugin versions.

#### Acceptance Criteria

1. THE Payload_Encoder SHALL include a `schema_version` field set to `"1.0"` in the root of the Payload JSON.
2. THE Payload_Encoder SHALL include a `plugin_version` field containing the plugin version string from the plugin manifest.
3. THE Payload_Encoder SHALL include a `generated_at` field containing the ISO 8601 UTC timestamp of payload creation.

### Requirement 9: Share Link Output Format

**User Story:** As a migration user working in any IDE or terminal, I want the share link to be clearly formatted and easy to click or copy, so that I can use it regardless of my development environment.

#### Acceptance Criteria

1. THE Plugin SHALL output the Share_Link on its own line, prefixed with a descriptive label.
2. THE Plugin SHALL output the Share_Link as plain text (not wrapped in markdown link syntax) so that terminal environments can render it as clickable.
3. WHEN the Share_Link is generated, THE Plugin SHALL also output the raw URL on a separate line for manual copy-paste in environments where link detection fails.

### Requirement 10: Feedback Phase Status Integration

**User Story:** As the plugin state machine, I want the feedback and sharing flow to integrate cleanly with phase status tracking, so that the migration state remains consistent.

#### Acceptance Criteria

1. WHEN the user completes feedback and sharing after Estimate, THE Plugin SHALL set `phases.feedback` to `"completed"` using the Phase Status Update Protocol.
2. WHEN the user declines feedback and sharing after Estimate, THE Plugin SHALL set `phases.feedback` to `"completed"` using the Phase Status Update Protocol.
3. WHEN the Generate phase completes and `phases.feedback` is still `"pending"`, THE Plugin SHALL set `phases.feedback` to `"completed"` regardless of whether the user shares the plan.
4. THE Plugin SHALL record sharing activity in `$MIGRATION_DIR/feedback.json` with fields: `share_link_presented` (boolean), `share_link_generated_at` (ISO 8601 or null), and `share_checkpoint` (one of: `"after_estimate"`, `"after_generate"`).
