# Heroku Discovery Schema

Schema for `heroku-resource-inventory.json`, produced by the Discover phase orchestrator (`discover.md`).

**Convention**: Values shown as `X|Y` in examples indicate allowed alternatives — use exactly one value per field, not the literal pipe character.

---

## heroku-resource-inventory.json (Phase 1 output)

Complete inventory of discovered Heroku resources. Uses a **flat resource model** — no clustering, no dependency graphs, no topological sorting. Resources are grouped by the `heroku_app` field only.

```json
{
  "metadata": {
    "discovery_timestamp": "2026-03-15T10:30:00Z",
    "total_apps_discovered": 4,
    "discovery_sources": ["terraform", "procfile"],
    "confidence": "full|reduced",
    "confidence_note": "Terraform had parse errors on some files (if reduced)"
  },
  "apps": [
    {
      "app_name": "my-web-app",
      "app_id": "01234567-89ab-cdef-0123-456789abcdef",
      "heroku_generation": "cedar|fir|unknown",
      "generation_action": "detect_only",
      "generation_diagnostics": [],
      "space": null,
      "discovery_status": "success|discovery_failed",
      "failure_reason": null,
      "procfile_parse_warning": null,
      "app_json_parse_warning": null
    }
  ],
  "resources": [
    {
      "resource_id": "formation:my-web-app:web",
      "resource_type": "formation",
      "heroku_app": "my-web-app",
      "config": {}
    }
  ],
  "billing_profile": {},
  "terraform_metadata": {}
}
```

---

## Top-Level Sections

### `metadata` (REQUIRED)

Report-level information about the discovery run.

| Field                   | Type              | Required | Description                                                                                                                                                      |
| ----------------------- | ----------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `discovery_timestamp`   | string (ISO 8601) | ✅       | When discovery was executed                                                                                                                                      |
| `total_apps_discovered` | integer           | ✅       | Count of Heroku apps found                                                                                                                                       |
| `discovery_sources`     | string[]          | ✅       | Sources used: `"terraform"`, `"procfile"`, `"billing"`                                                                                                           |
| `confidence`            | string            | ✅       | `"full"` (Terraform files present and parsed successfully) or `"reduced"` (Partial data, e.g., Terraform parse errors on some files, missing expected resources) |
| `confidence_note`       | string            | ❌       | Explanation when confidence is `"reduced"`                                                                                                                       |

### `apps[]` (REQUIRED)

Per-app metadata entries. One entry per discovered Heroku app.

| Field                    | Type           | Required | Description                                                                                               |
| ------------------------ | -------------- | -------- | --------------------------------------------------------------------------------------------------------- |
| `app_name`               | string         | ✅       | Heroku app name                                                                                           |
| `app_id`                 | string (UUID)  | ✅       | Heroku app UUID                                                                                           |
| `heroku_generation`      | string         | ✅       | `"cedar"`, `"fir"`, or `"unknown"`                                                                        |
| `generation_action`      | string         | ✅       | Always `"detect_only"` in v1                                                                              |
| `generation_diagnostics` | string[]       | ✅       | Diagnostic reasons (empty array if resolved cleanly; contains `"generation_unresolved"` on timeout/error) |
| `space`                  | string \| null | ✅       | Private Space name, or `null` if not in a space                                                           |
| `discovery_status`       | string         | ✅       | `"success"` or `"discovery_failed"`                                                                       |
| `failure_reason`         | string \| null | ✅       | Error description when `discovery_status` is `"discovery_failed"`, otherwise `null`                       |
| `procfile_parse_warning` | string \| null | ✅       | Warning text if Procfile parsing failed, otherwise `null`                                                 |
| `app_json_parse_warning` | string \| null | ✅       | Warning text if app.json parsing failed, otherwise `null`                                                 |

### `resources[]` (REQUIRED)

Flat array of all discovered resources. **No nesting, no clustering.**

| Field           | Type   | Required | Description                                               |
| --------------- | ------ | -------- | --------------------------------------------------------- |
| `resource_id`   | string | ✅       | Unique identifier (format below)                          |
| `resource_type` | string | ✅       | One of: `"formation"`, `"addon"`, `"space"`, `"pipeline"` |
| `heroku_app`    | string | ✅       | App name this resource belongs to, or `"unassociated"`    |
| `config`        | object | ✅       | Type-specific configuration (see per-type schemas below)  |

### `billing_profile` (OPTIONAL — present when billing data available)

| Field                | Type     | Required | Description                                  |
| -------------------- | -------- | -------- | -------------------------------------------- |
| `available`          | boolean  | ✅       | Whether billing data was successfully parsed |
| `total_monthly_cost` | number   | ✅       | Total monthly spend in declared currency     |
| `currency`           | string   | ✅       | ISO 4217 currency code (e.g., `"USD"`)       |
| `billing_period`     | string   | ✅       | YYYY-MM format billing period                |
| `line_items`         | object[] | ✅       | Per-resource cost breakdown                  |

#### `billing_profile.line_items[]`

| Field           | Type   | Required | Description                          |
| --------------- | ------ | -------- | ------------------------------------ |
| `resource_name` | string | ✅       | App or resource name                 |
| `category`      | string | ✅       | `"dyno"`, `"addon"`, or `"platform"` |
| `cost`          | number | ✅       | Cost amount in billing currency      |

### `terraform_metadata` (OPTIONAL — present when Terraform discovery ran)

| Field                      | Type     | Required | Description                                                               |
| -------------------------- | -------- | -------- | ------------------------------------------------------------------------- |
| `found`                    | boolean  | ✅       | Whether Terraform files with `heroku_*` resources were found              |
| `tf_files_scanned`         | integer  | ✅       | Number of `.tf` files scanned                                             |
| `resource_types_extracted` | string[] | ✅       | List of extracted resource types (e.g., `"heroku_app"`, `"heroku_addon"`) |
| `parse_warnings`           | string[] | ✅       | Any parse warnings encountered during extraction                          |

---

## Resource ID Formats

Deterministic ID format per resource type:

| Resource Type | ID Format                                 | Example                                         |
| ------------- | ----------------------------------------- | ----------------------------------------------- |
| `formation`   | `formation:{app_name}:{process_type}`     | `formation:my-web-app:web`                      |
| `addon`       | `addon:{app_name}:{addon_service}:{plan}` | `addon:my-web-app:heroku-postgresql:standard-0` |
| `space`       | `space:{space_name}`                      | `space:my-private-space`                        |
| `pipeline`    | `pipeline:{pipeline_name}`                | `pipeline:my-pipeline`                          |

---

## Per-Type Config Schemas

### `formation` config

```json
{
  "process_type": "web|worker|release|clock|<custom>",
  "command": "npm start",
  "dyno_type": "standard-1x|standard-2x|performance-m|performance-l|private-s|private-m|private-l",
  "quantity": 2
}
```

| Field          | Type            | Required | Description                     |
| -------------- | --------------- | -------- | ------------------------------- |
| `process_type` | string          | ✅       | Process type name from Procfile |
| `command`      | string          | ✅       | Start command from Procfile     |
| `dyno_type`    | string          | ✅       | Heroku dyno size                |
| `quantity`     | integer (0–100) | ✅       | Number of dynos running         |

### `addon` config

```json
{
  "addon_service": "heroku-postgresql",
  "plan": "standard-0",
  "provider": "heroku",
  "connection_pooling": true
}
```

| Field           | Type   | Required | Description         |
| --------------- | ------ | -------- | ------------------- |
| `addon_service` | string | ✅       | Add-on service name |
| `plan`          | string | ✅       | Plan tier name      |
| `provider`      | string | ✅       | Add-on provider     |

**Additional fields by addon type:**

- **heroku-postgresql**: `connection_pooling` (boolean)
- **heroku-redis**: `ha_enabled` (boolean), `encryption_in_transit` (boolean), `redis_version` (string)
- **heroku-kafka**: `topic_count` (integer), `partitions_per_topic` (integer), `replication_factor` (integer)
- **Other add-ons**: No additional required fields

### `space` config

```json
{
  "space_name": "my-private-space",
  "region": "virginia",
  "shield": false,
  "peering": {
    "detected": true,
    "vpc_id": "vpc-0123456789abcdef0",
    "peer_cidr": "10.0.0.0/16"
  }
}
```

| Field               | Type           | Required | Description                                         |
| ------------------- | -------------- | -------- | --------------------------------------------------- |
| `space_name`        | string         | ✅       | Private Space name                                  |
| `region`            | string         | ✅       | Heroku region                                       |
| `shield`            | boolean        | ✅       | Whether Shield compliance is enabled                |
| `peering`           | object         | ✅       | VPC peering information                             |
| `peering.detected`  | boolean        | ✅       | Whether VPC peering was found                       |
| `peering.vpc_id`    | string \| null | ✅       | Peered VPC ID (null if not detected or unavailable) |
| `peering.peer_cidr` | string \| null | ✅       | Peer CIDR block (null if not detected)              |

### `pipeline` config

```json
{
  "pipeline_name": "my-pipeline",
  "stages": [
    { "stage": "development", "app": "my-web-app-dev" },
    { "stage": "staging", "app": "my-web-app-staging" },
    { "stage": "production", "app": "my-web-app" }
  ],
  "review_apps_enabled": true,
  "detection_status": "detect-only"
}
```

| Field                 | Type     | Required | Description                                                          |
| --------------------- | -------- | -------- | -------------------------------------------------------------------- |
| `pipeline_name`       | string   | ✅       | Pipeline name                                                        |
| `stages`              | object[] | ✅       | Stage definitions                                                    |
| `stages[].stage`      | string   | ✅       | Stage name: `"review"`, `"development"`, `"staging"`, `"production"` |
| `stages[].app`        | string   | ✅       | App name assigned to this stage                                      |
| `review_apps_enabled` | boolean  | ✅       | Whether Review Apps are enabled                                      |
| `detection_status`    | string   | ✅       | Always `"detect-only"` in v1                                         |

---

## Forbidden Fields

The following fields MUST NOT appear anywhere in `heroku-resource-inventory.json`. Their presence indicates accidental use of the GCP clustering model:

- `cluster_id`
- `creation_order_depth`
- `edges`
- `dependencies`
- `must_migrate_together`

---

## Grouping Rules

1. All resources in `resources[]` are grouped by the `heroku_app` field value.
2. Resources belonging to the same Heroku app share an identical `heroku_app` value.
3. Resources that cannot be associated with exactly one app use `heroku_app: "unassociated"`.
4. Typical "unassociated" resources: spaces (shared across apps), pipelines (span multiple apps).
5. The `resources[]` array is flat — no nesting under app-level containers.

---

## Confidence Levels

| Level     | Meaning                                                                 | When Used                                                                       |
| --------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `full`    | Terraform files present and parsed successfully                         | Terraform discovery completed without parse errors                              |
| `reduced` | Partial data — Terraform had parse errors or missing expected resources | Some `.tf` files could not be parsed, or expected resource types were not found |

---

## Complete Example

```json
{
  "metadata": {
    "discovery_timestamp": "2026-03-15T10:30:00Z",
    "total_apps_discovered": 4,
    "discovery_sources": ["terraform", "procfile"],
    "confidence": "full"
  },
  "apps": [
    {
      "app_name": "my-web-app",
      "app_id": "01234567-89ab-cdef-0123-456789abcdef",
      "heroku_generation": "cedar",
      "generation_action": "detect_only",
      "generation_diagnostics": [],
      "space": null,
      "discovery_status": "success",
      "failure_reason": null,
      "procfile_parse_warning": null,
      "app_json_parse_warning": null
    },
    {
      "app_name": "my-worker-app",
      "app_id": "fedcba98-7654-3210-fedc-ba9876543210",
      "heroku_generation": "fir",
      "generation_action": "detect_only",
      "generation_diagnostics": [],
      "space": "my-private-space",
      "discovery_status": "success",
      "failure_reason": null,
      "procfile_parse_warning": null,
      "app_json_parse_warning": null
    }
  ],
  "resources": [
    {
      "resource_id": "formation:my-web-app:web",
      "resource_type": "formation",
      "heroku_app": "my-web-app",
      "config": {
        "process_type": "web",
        "command": "npm start",
        "dyno_type": "standard-2x",
        "quantity": 2
      }
    },
    {
      "resource_id": "formation:my-web-app:worker",
      "resource_type": "formation",
      "heroku_app": "my-web-app",
      "config": {
        "process_type": "worker",
        "command": "node worker.js",
        "dyno_type": "standard-1x",
        "quantity": 1
      }
    },
    {
      "resource_id": "addon:my-web-app:heroku-postgresql:standard-0",
      "resource_type": "addon",
      "heroku_app": "my-web-app",
      "config": {
        "addon_service": "heroku-postgresql",
        "plan": "standard-0",
        "provider": "heroku",
        "connection_pooling": true
      }
    },
    {
      "resource_id": "addon:my-web-app:heroku-redis:premium-0",
      "resource_type": "addon",
      "heroku_app": "my-web-app",
      "config": {
        "addon_service": "heroku-redis",
        "plan": "premium-0",
        "provider": "heroku",
        "ha_enabled": true,
        "encryption_in_transit": true,
        "redis_version": "7.0"
      }
    },
    {
      "resource_id": "addon:my-web-app:papertrail:choklad",
      "resource_type": "addon",
      "heroku_app": "my-web-app",
      "config": {
        "addon_service": "papertrail",
        "plan": "choklad",
        "provider": "papertrail"
      }
    },
    {
      "resource_id": "space:my-private-space",
      "resource_type": "space",
      "heroku_app": "unassociated",
      "config": {
        "space_name": "my-private-space",
        "region": "virginia",
        "shield": false,
        "peering": {
          "detected": true,
          "vpc_id": "vpc-0123456789abcdef0",
          "peer_cidr": "10.0.0.0/16"
        }
      }
    },
    {
      "resource_id": "pipeline:my-pipeline",
      "resource_type": "pipeline",
      "heroku_app": "unassociated",
      "config": {
        "pipeline_name": "my-pipeline",
        "stages": [
          { "stage": "development", "app": "my-web-app-dev" },
          { "stage": "staging", "app": "my-web-app-staging" },
          { "stage": "production", "app": "my-web-app" }
        ],
        "review_apps_enabled": true,
        "detection_status": "detect-only"
      }
    }
  ],
  "billing_profile": {
    "available": true,
    "total_monthly_cost": 450.00,
    "currency": "USD",
    "billing_period": "2026-02",
    "line_items": [
      { "resource_name": "my-web-app", "category": "dyno", "cost": 100.00 },
      { "resource_name": "my-web-app", "category": "addon", "cost": 200.00 },
      { "resource_name": "my-web-app", "category": "platform", "cost": 50.00 },
      { "resource_name": "my-worker-app", "category": "dyno", "cost": 50.00 },
      { "resource_name": "my-worker-app", "category": "addon", "cost": 50.00 }
    ]
  },
  "terraform_metadata": {
    "found": true,
    "tf_files_scanned": 5,
    "resource_types_extracted": ["heroku_app", "heroku_addon", "heroku_formation"],
    "parse_warnings": []
  }
}
```

---

## Validation Checklist (used by Completion Handoff Gate)

1. ✅ `heroku-resource-inventory.json` exists with at least one resource entry
2. ✅ `metadata.discovery_timestamp` is set (ISO 8601)
3. ✅ `metadata.total_apps_discovered` is set (integer ≥ 0)
4. ✅ `metadata.discovery_sources` is a non-empty array
5. ✅ `metadata.confidence` is `"full"` or `"reduced"`
6. ✅ Every entry in `resources[]` has: `resource_id`, `resource_type`, `heroku_app`, `config`
7. ✅ Every entry in `apps[]` has: `app_name`, `heroku_generation`, `generation_action`, `discovery_status`
8. ✅ No forbidden clustering fields present anywhere in the document
9. ✅ If Terraform discovery ran → resources include Terraform-sourced entries
10. ✅ If Terraform had parse errors → `metadata.confidence` is `"reduced"`
11. ✅ If billing discovery ran → `billing_profile` section present with `available: true`
