# Implementation Plan: Migration Telemetry Sharing

## Overview

This plan restructures the feedback checkpoints in the GCP-to-AWS migration plugin and adds a "share your plan" mechanism. Implementation is markdown-driven — all "code" is agent instructions in markdown reference files. The encoding logic uses shell commands (`gzip`, `base64`) and Node.js one-liners available in the agent runtime. Property-based tests use fast-check (JavaScript PBT library).

## Tasks

-
  1. [ ] Restructure SKILL.md feedback checkpoints
  - [ ] 1.1 Remove the post-Discover feedback checkpoint from SKILL.md
    - In the "Feedback checkpoints" section, delete the "After Discover" block that offers feedback with [A] Now / [B] Wait options
    - Replace with instruction: "After Discover: No prompt. Proceed directly to Clarify."
    - Update the numbered workflow step 8 to remove the Discover feedback logic
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ] 1.2 Add combined feedback+share prompt after Estimate in SKILL.md
    - In the "Feedback checkpoints" section, replace the "After Estimate" block with the new combined 3-option prompt: [A] Send feedback & share plan, [B] Send feedback only, [C] No thanks, continue to Generate
    - Add instruction to load `references/phases/feedback/payload-encoder.md` when user selects option A
    - Add instruction to load `references/phases/feedback/feedback.md` when user selects option A or B
    - Add instruction to set `phases.feedback` to `"completed"` when user selects option C
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 1.3 Add share-only prompt after Generate in SKILL.md
    - In the "Feedback checkpoints" section, add new "After Generate" block with 2-option prompt: [A] Share completed plan, [B] No thanks, finish
    - Add instruction to load `references/phases/feedback/payload-encoder.md` when user selects option A
    - Add instruction to set `phases.feedback` to `"completed"` regardless of user choice
    - Specify that feedback questions are NOT re-presented after Generate
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 10.3_

-
  2. [ ] Create payload-encoder.md
  - [ ] 2.1 Create the payload assembly section in payload-encoder.md
    - Create new file at `references/phases/feedback/payload-encoder.md`
    - Write Step 1: Input artifact loading (preferences.json, estimation-*.json, gcp-resource-inventory.json, ai-workload-profile.json, billing-profile.json)
    - Write Step 2: Payload JSON assembly per the schema (schema_version, plugin_version, generated_at, clarify_answers, recommendation, cost_summary, detected_services, resource_names, workload_types, spend_band)
    - Include spend band derivation logic with source priority (billing-profile → estimation-infra → estimation-billing → "unknown")
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 8.1, 8.2, 8.3_

  - [ ] 2.2 Add secret redaction filter to payload-encoder.md
    - Write Step 3: Secret Redaction, scanning preferences.json field values for known secret patterns before encoding
    - Include regex patterns: AWS access key ID (`AKIA[A-Z0-9]{16}`), private key headers, connection strings with passwords, high-entropy strings in secret/password/token/key fields
    - Specify redaction behavior: replace matched values with `"[REDACTED]"`
    - Add 5-second timeout for pathological input handling
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ] 2.3 Add compression, encoding, and truncation logic to payload-encoder.md
    - Write Step 4: Encoding — serialize to minified JSON, compress with gzip, encode as Base64URL
    - Include both shell and Node.js encoding commands:
      - Shell: `echo '<json>' | gzip -c | base64 | tr '+/' '-_' | tr -d '='`
      - Node: `node -e "const z=require('zlib');const b=z.gzipSync(Buffer.from(JSON.stringify(payload)));console.log(b.toString('base64url'))"`
    - Write Step 5: Size check — if Base64URL string > 8,192 characters, apply truncation in priority order (resource_names → inferred answers → default answers → rationale → excess detected_services)
    - Specify never-remove fields: schema_version, plugin_version, generated_at, recommendation.path, cost_summary, workload_types, spend_band
    - Write Step 6: URL construction — `https://aws.amazon.com/startups/migrate/connect#<base64url_payload>`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 2.4 Add consent disclosure and output formatting to payload-encoder.md
    - Write Step 7: Consent Disclosure — display the exact disclosure text before the share link
    - Include both templates (after-Estimate combined, after-Generate share-only)
    - Write Step 8: Output Formatting — share link on its own line with descriptive label, plain text (no markdown link syntax), duplicate URL for copy-paste
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 9.1, 9.2, 9.3_

  - [ ] 2.5 Add error handling to payload-encoder.md
    - Write error handling section covering: missing preferences.json, missing estimation artifacts, missing resource inventory, missing billing profile, compression failure, payload too large, unreadable plugin manifest, malformed JSON
    - Each error case produces a user-visible message and allows the flow to continue
    - _Requirements: 5.3, 5.4 (edge cases from design Error Handling table)_

-
  3. [ ] Checkpoint - Ensure payload-encoder.md is complete and internally consistent
  - Ensure all tests pass, ask the user if questions arise.

-
  4. [ ] Modify estimate.md Phase Completion
  - [ ] 4.1 Update estimate.md Phase Completion to invoke the combined prompt
    - In the "Phase Completion" section, after `HANDOFF_OK` and phase status update, add logic to check if `phases.feedback == "pending"`
    - If pending: present the combined 3-option prompt (consent disclosure + feedback + share)
    - If user picks A: load `references/phases/feedback/feedback.md`, then load `references/phases/feedback/payload-encoder.md`
    - If user picks B: load `references/phases/feedback/feedback.md` only
    - If user picks C: set `phases.feedback` to `"completed"` and proceed
    - After feedback/share completes: output "Proceeding to Phase 5: Generate Migration Artifacts."
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 10.1, 10.2_

-
  5. [ ] Modify generate.md Phase Completion
  - [ ] 5.1 Update generate.md Phase Completion to invoke the share-only prompt
    - In the "Phase Completion" section, after `HANDOFF_OK` and phase status update, add the share-only 2-option prompt
    - Present consent disclosure text before the share link options
    - If user picks A: load `references/phases/feedback/payload-encoder.md`
    - If user picks B: proceed to mark complete
    - Regardless of choice: set `phases.feedback` to `"completed"` if still `"pending"`
    - Do NOT present the 5 feedback survey questions
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 10.3_

-
  6. [ ] Update feedback.md to handle the new flow
  - [ ] 6.1 Update feedback.md to record sharing activity in feedback.json
    - Add new fields to the feedback.json write step: `share_link_presented` (boolean), `share_link_generated_at` (ISO 8601 or null), `share_checkpoint` (one of: "after_estimate", "after_generate")
    - The checkpoint value is passed as context from the calling prompt (SKILL.md / estimate.md / generate.md)
    - _Requirements: 10.4_

-
  7. [ ] Checkpoint - Ensure all markdown reference files are consistent
  - Ensure all tests pass, ask the user if questions arise.

-
  8. [ ] Property-based tests for encoding logic
  - [ ]* 8.1 Write property test: Payload Data Completeness
    - **Property 1: Payload Data Completeness**
    - Use fast-check to generate arbitrary preferences (1–30 Q&A pairs), estimation artifacts with recommendation path/rationale, and resource inventories (0–100 resources)
    - Assert: assembled payload contains all N Clarify answers, recommendation rationale, all M service types, and all K resource name/type pairs
    - **Validates: Requirements 4.1, 4.3, 4.5, 4.8**

  - [ ]* 8.2 Write property test: Cost Delta Correctness
    - **Property 2: Cost Delta Correctness**
    - Use fast-check to generate arbitrary pairs of numeric values (current_gcp_monthly, projected_aws_monthly)
    - Assert: `cost_summary.delta == projected_aws_monthly - current_gcp_monthly`
    - **Validates: Requirements 4.4**

  - [ ]* 8.3 Write property test: Spend Band Derivation
    - **Property 3: Spend Band Derivation**
    - Use fast-check to generate arbitrary non-negative monthly spend amounts
    - Assert: correct spend_band value based on thresholds (under-10k, 10k-50k, 50k-100k, over-100k)
    - **Validates: Requirements 4.7**

  - [ ]* 8.4 Write property test: Encoding Round-Trip
    - **Property 4: Encoding Round-Trip**
    - Use fast-check to generate arbitrary valid Migration_Profile JSON objects
    - Assert: gzip + Base64URL encoding then Base64URL decoding + gunzip produces identical JSON
    - Use Node.js `zlib.gzipSync`/`gunzipSync` and `Buffer.toString('base64url')`/`Buffer.from(str, 'base64url')`
    - **Validates: Requirements 5.1**

  - [ ]* 8.5 Write property test: Size Limit Guarantee
    - **Property 5: Size Limit Guarantee**
    - Use fast-check to generate oversized Migration_Profiles (50+ resources, 30 Q&A pairs, long strings)
    - Assert: final Base64URL-encoded payload ≤ 8,192 characters
    - Assert: truncation order removes resource_names first, then inferred answers, then default answers, then rationale, then excess detected_services
    - Assert: never-remove fields are always present
    - **Validates: Requirements 5.3, 5.4**

  - [ ]* 8.6 Write property test: Secret Redaction
    - **Property 6: Secret Redaction**
    - Use fast-check to generate preferences.json with field values containing AWS access keys (`AKIA[A-Z0-9]{16}`), private key headers, connection strings with passwords, and high-entropy strings in secret/password/token/key fields
    - Assert: matching values in the assembled payload are `"[REDACTED]"` and original secret material is absent
    - **Validates: Requirements 7.2, 7.3, 7.5, 7.7**

-
  9. [ ] Integration test: encode a real migration profile and verify decode
  - [ ]* 9.1 Write integration test for end-to-end encoding verification
    - Create a representative migration profile JSON (preferences, estimation, resource inventory)
    - Encode via both shell command (`gzip -c | base64 | tr '+/' '-_' | tr -d '='`) and Node.js (`zlib.gzipSync + toString('base64url')`)
    - Verify both produce identical output
    - Decode the result and verify it matches the original JSON
    - Verify the final URL format is `https://aws.amazon.com/startups/migrate/connect#<payload>`
    - **Validates: Requirements 5.1, 5.2**

-
  10. [ ] Final checkpoint - Ensure all files are consistent and tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The implementation is markdown-driven: all "code" is agent instructions in `.md` reference files
- Shell commands (`gzip`, `base64`, `tr`) and Node.js one-liners are the encoding runtime
- Tests use fast-check (JavaScript PBT library) since encoding is JS/shell based
- The `feedback-trace.md` file requires no changes

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "2.5"] },
    { "id": 4, "tasks": ["4.1", "5.1", "6.1"] },
    { "id": 5, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5", "8.6"] },
    { "id": 6, "tasks": ["9.1"] }
  ]
}
```
