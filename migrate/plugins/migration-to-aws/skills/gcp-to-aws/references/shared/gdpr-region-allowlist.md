# GDPR Region Allowlist and Closest-EU Mapping

**Canonical reference.** This is the single source of truth for the EU region allowlist and closest-EU region suggestions used when a migration declares GDPR (`preferences.json → compliance` contains `"gdpr"`). Clarify, Design, and the `design-refs/*.md` conditional rules all reference this file — do not inline or duplicate this list elsewhere.

**Scope note:** This allowlist enforces the **data-residency and cross-border-replication policy stated in Clarify Q2** for GDPR-declared migrations. It is a plugin policy, not legal advice, and it does not determine whether a workload's actual data processing falls in scope of GDPR, whether a lawful basis exists, or whether any particular AWS region satisfies a specific customer's regulatory posture. Confirm with legal/compliance counsel before relying on this list for a real migration.

---

## EU Region Allowlist

AWS commercial `eu-*` regions. A `target_region` is GDPR-allowlisted if and only if it appears in this table.

| Region code    | Location            |
| -------------- | ------------------- |
| `eu-west-1`    | Ireland             |
| `eu-west-2`    | London, UK          |
| `eu-west-3`    | Paris, France       |
| `eu-central-1` | Frankfurt, Germany  |
| `eu-central-2` | Zurich, Switzerland |
| `eu-north-1`   | Stockholm, Sweden   |
| `eu-south-1`   | Milan, Italy        |
| `eu-south-2`   | Spain               |

**UK note:** `eu-west-2` (London) is included using AWS's standard commercial `eu-*` region naming. Post-Brexit, UK GDPR and EU GDPR are separate (though currently aligned) legal regimes. This skill does not distinguish between them — if a migration specifically needs to satisfy UK GDPR requirements distinct from EU GDPR, confirm region and safeguard requirements with counsel; do not rely on this allowlist alone.

**Switzerland note:** `eu-central-2` is included because it is commonly grouped with EU-adjacent data-residency requirements, though Switzerland is not an EU member state and has its own data protection framework (FADP) that is not identical to GDPR. Treat inclusion here as a convenience default, not a legal determination.

**Not modeled in v1:** This skill does not separately model UK GDPR vs EU GDPR, Swiss FADP, or any other EU-adjacent framework as a distinct `compliance` value. If a future migration needs that distinction, it should be added as a new compliance option (not folded silently into `"gdpr"`).

---

## Closest-EU Region Mapping

Used by the Clarify GDPR region cross-check (see `clarify-global.md`) to suggest a specific EU region in option A ("Switch target region to `{closest EU region}`"). This mapping is a **default suggestion**, not a requirement — the user can pick any allowlisted region.

### From GCP source region (when discovery identifies the source GCP region)

| Source GCP region             | Suggested AWS EU region                                                           |
| ----------------------------- | --------------------------------------------------------------------------------- |
| `europe-west1` (Belgium)      | `eu-west-1`                                                                       |
| `europe-west2` (London)       | `eu-west-2`                                                                       |
| `europe-west3` (Frankfurt)    | `eu-central-1`                                                                    |
| `europe-west4` (Netherlands)  | `eu-west-1`                                                                       |
| `europe-west6` (Zurich)       | `eu-central-2`                                                                    |
| `europe-west8` (Milan)        | `eu-south-1`                                                                      |
| `europe-west9` (Paris)        | `eu-west-3`                                                                       |
| `europe-north1` (Finland)     | `eu-north-1`                                                                      |
| `europe-southwest1` (Madrid)  | `eu-south-2`                                                                      |
| Any other `europe-*` region   | `eu-west-1` (fallback)                                                            |
| Any non-`europe-*` GCP region | `eu-west-1` (fallback — largest EU region, no geography signal to prefer another) |

### From a previously-resolved non-EU AWS region (when Q1 already resolved before the GDPR mismatch is caught)

| Non-EU AWS region (examples)                         | Suggested AWS EU region |
| ---------------------------------------------------- | ----------------------- |
| `us-east-1`, `us-east-2`, `us-west-1`, `us-west-2`   | `eu-west-1`             |
| `ap-southeast-1`, `ap-southeast-2`, `ap-northeast-1` | `eu-central-1`          |
| `sa-east-1`                                          | `eu-west-1`             |
| Any other non-EU region                              | `eu-west-1` (fallback)  |

**Fallback rule:** If the source region (GCP or previously-resolved AWS) is not in either table above, suggest `eu-west-1`. Do not block on an unmapped source — always produce a suggestion.

---

## Usage

1. **Clarify (`clarify-global.md` Q1/Q2):** When `compliance` includes `"gdpr"` and the resolved `target_region` is not in the EU Region Allowlist table above, look up the closest-EU suggestion from the mapping tables and present it as option A in the GDPR region cross-check prompt.
2. **Design (precondition gate):** Check `target_region` against the EU Region Allowlist table. Do not re-derive the list — read it from this file.
3. **`design-refs/storage.md` and `design-refs/database.md`:** When determining whether a replication target is "in the EU" for GDPR cross-region gating, check the target region against the EU Region Allowlist table here.

**Maintenance note:** If AWS adds or retires an `eu-*` region, update only this file. Do not add region codes to `clarify-global.md`, `design-infra.md`, or any `design-refs/*.md` file directly.
