# Fast-Path Table — Add-On → AWS Service Mappings

## Description

This table provides deterministic mappings from Heroku add-ons to AWS service equivalents. The Design Engine uses this table during the design phase to automatically map known add-ons without requiring specialist evaluation. Add-ons matched here receive a confidence level of `"deterministic"`.

## Lookup Table

> **Data:** [`knowledge/design/fast-path-addons.json`](../../knowledge/design/fast-path-addons.json)
>
> The add-on → AWS service mappings are maintained as structured data in that JSON
> file. Read the `rows` map keyed by NORMALIZED add-on name; each row carries
> `type` (`single` or `composite`), `aws_services`, and `notes`. A discovered
> add-on name is normalized before matching (strip a leading `heroku-`, hyphens →
> spaces, lowercase, then apply the `_prefix_aliases`); matching is exact
> full-string (partial matches are invalid). All matches produce confidence
> `"deterministic"`.

## Interpretation Notes

- **Matching rule**: The add-on name from the inventory is matched against each row's key (the normalized add-on name) using **exact case-insensitive string comparison**. Partial matches (e.g., "Paper" matching "Papertrail") are NOT valid and must be treated as unmatched.
- **Confidence level**: All matches from this table produce a confidence level of `"deterministic"` in the design output.
- **Single mappings**: Map the source add-on to exactly one AWS service.
- **Composite mappings**: Map the source add-on to multiple AWS services that together replicate the source functionality. All listed services must appear in the design output as a single composite mapping with one `"deterministic"` confidence level assigned to the group.
- **Specialist gate**: Any add-on whose name does not exactly match (case-insensitive) an entry in this table is marked as `"Deferred — specialist engagement"` with no automated AWS mapping applied. The deferred record must include: add-on name, add-on plan, provider, reason for deferral, and a recommendation to engage the AWS account team.

## Error Handling

If a discovered add-on's name is not found in this table (no exact case-insensitive match), mark it as deferred:

> "Not found in Fast_Path_Table. Deferred to specialist engagement — engage AWS account team for replacement selection."
