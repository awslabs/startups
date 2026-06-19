# Generate Phase: Rollback Script Generation

> Loaded by generate.md after generate-artifacts-scripts.md completes (migration scripts generated).

**Execute ALL steps in order. Do not skip or optimize.**

## Overview

Transform the migration plan (`generation-infra.json`) and design (`aws-design.json`) into a numbered rollback script that reverts each migration step. The rollback script is the inverse of scripts 02–04: it restores traffic, data paths, and secrets back to GCP if the migration fails validation or the customer decides to abort.

**Outputs:**

- `scripts/06-rollback-migration.sh` — Per-service rollback with decision tree
- `scripts/ROLLBACK_GUIDE.md` — Human-readable rollback decision tree

## Philosophy

- **Rollback is not disaster recovery.** It assumes GCP resources still exist (they should — the migration scripts copy data, they don't delete sources).
- **Rollback is ordered in reverse.** If migration goes 01→02→03→04→05, rollback goes in reverse dependency order.
- **Rollback is safe by default.** Like forward scripts, rollback defaults to dry-run mode and requires `--execute` to make changes.
- **Partial rollback is supported.** Each service block can be run independently via `--only <service>` flag.
- **Rollback does NOT destroy AWS resources.** It redirects traffic back to GCP but leaves AWS infra standing for retry. Use `terraform destroy` separately if full teardown is desired.

## Prerequisites

Read the following artifacts from `$MIGRATION_DIR/`:

- `aws-design.json` (REQUIRED) — AWS architecture design with cluster-level resource mappings
- `generation-infra.json` (REQUIRED) — Migration plan with timeline and service assignments
- `preferences.json` (REQUIRED) — User preferences including target region, sizing
- `scripts/` directory (REQUIRED) — Forward migration scripts must already exist

If any REQUIRED file is missing: **STOP**. Output: "Missing required artifact: [filename]. Complete the prior phase that produces it."

## Step 1: Detect Rollback Targets

Scan `aws-design.json` clusters[].resources[] and determine which services have forward migration scripts. Set boolean flags:

- **rollback_database**: true if `02-migrate-data.sh` exists AND has_databases
- **rollback_containers**: true if `03-migrate-containers.sh` exists AND has_containers
- **rollback_secrets**: true if `04-migrate-secrets.sh` exists AND has_secrets
- **rollback_dns**: true if any resource has `aws_service` containing "Route 53" or design includes DNS cutover
- **rollback_loadbalancer**: true if any resource has `aws_service` containing "ALB" or "NLB"

Report detected rollback targets to user: "Rollback targets detected: [list active flags]"

## Step 2: Generate 06-rollback-migration.sh

### Script Rules

- Defaults to **dry-run mode** — requires `--execute` flag to make changes
- Supports `--only <service>` to rollback a single service (values: dns, lb, containers, database, secrets)
- Logs all actions to `$MIGRATION_DIR/logs/rollback-<timestamp>.log`
- Uses `set -euo pipefail` for safety
- Each section has a **pre-check** (verify GCP resource still exists) and **action** (redirect traffic)
- Script exits with summary: which services were rolled back, which were skipped

### Script Structure

```bash
#!/usr/bin/env bash
set -euo pipefail
# Migration Rollback: AWS → GCP (restore original state)
# Usage: ./06-rollback-migration.sh [--execute] [--only <service>]
#
# This script reverses the migration by redirecting traffic and connections
# back to GCP. It does NOT destroy AWS resources — use terraform destroy separately.
#
# Rollback order (reverse of migration):
#   1. DNS / Load Balancer (redirect traffic first)
#   2. Application config (point apps back to GCP endpoints)
#   3. Secrets (restore GCP Secret Manager references)
#   4. Database (no data rollback needed if GCP source was preserved)
#   5. Containers (stop ECS/EKS tasks, restore Cloud Run traffic)
#
# Pre-conditions:
#   - GCP resources must still exist (migration scripts copy, they don't delete)
#   - GCP service accounts must still be active
#   - DNS TTLs from migration must have expired (check TTL before rollback)

DRY_RUN=true
ONLY_SERVICE=""
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="${MIGRATION_DIR:-./}/logs/rollback-${TIMESTAMP}.log"

[[ "${1:-}" == "--execute" ]] && DRY_RUN=false && shift
[[ "${1:-}" == "--only" ]] && ONLY_SERVICE="${2:-}" && shift 2

mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Migration Rollback ==="
echo "Mode: $([ "$DRY_RUN" = true ] && echo 'DRY RUN' || echo 'EXECUTE')"
echo "Scope: $([ -n "$ONLY_SERVICE" ] && echo "$ONLY_SERVICE only" || echo 'all services')"
echo "Log: $LOG_FILE"
echo ""

should_run() {
  [ -z "$ONLY_SERVICE" ] || [ "$ONLY_SERVICE" = "$1" ]
}

rollback_status=()

```

### Section: DNS & Load Balancer Rollback — IF rollback_dns OR rollback_loadbalancer

```bash
# === STEP 1: DNS & Load Balancer Rollback ===
if should_run "dns" || should_run "lb"; then
  echo "--- DNS / Load Balancer Rollback ---"
  
  # Pre-check: Verify GCP endpoint is still reachable
  GCP_ENDPOINT="" # TODO: Set from original GCP config
  
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would update DNS records to point back to GCP endpoint: $GCP_ENDPOINT"
    echo "[DRY RUN] Would update ALB/NLB target group to drain AWS targets"
  else
    echo "WARNING: Verify DNS TTL has expired before proceeding."
    echo "Current TTL may cause split-brain traffic for up to TTL seconds."
    read -p "DNS TTL expired? (yes/no): " ttl_confirm
    if [ "$ttl_confirm" != "yes" ]; then
      echo "ABORTED: Wait for DNS TTL to expire before rollback."
      exit 1
    fi
    
    # TODO: Update Route 53 records back to GCP IP
    # aws route53 change-resource-record-sets --hosted-zone-id $ZONE_ID --change-batch ...
    echo "DNS records updated to point to GCP."
  fi
  
  rollback_status+=("dns: $([ "$DRY_RUN" = true ] && echo 'dry-run' || echo 'rolled-back')")
fi

```

### Section: Container Rollback — IF rollback_containers

```bash
# === STEP 2: Container Rollback ===
if should_run "containers"; then
  echo "--- Container Rollback ---"
  
  # Pre-check: Verify Cloud Run service still exists
  # gcloud run services describe $SERVICE_NAME --region $GCP_REGION 2>/dev/null
  
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would scale down ECS service to 0 desired tasks"
    echo "[DRY RUN] Would restore Cloud Run traffic allocation to 100%"
  else
    # Scale down ECS (don't destroy — leave for potential retry)
    # aws ecs update-service --cluster $CLUSTER --service $SERVICE --desired-count 0
    
    # Restore Cloud Run traffic (if traffic was split during migration)
    # gcloud run services update-traffic $SERVICE --to-revisions=LATEST=100 --region $GCP_REGION
    
    echo "ECS scaled to 0. Cloud Run restored to 100% traffic."
  fi
  
  rollback_status+=("containers: $([ "$DRY_RUN" = true ] && echo 'dry-run' || echo 'rolled-back')")
fi

```

### Section: Database Rollback — IF rollback_database

```bash
# === STEP 3: Database Rollback ===
if should_run "database"; then
  echo "--- Database Rollback ---"
  
  # Pre-check: Verify Cloud SQL instance still exists and is accessible
  # gcloud sql instances describe $INSTANCE_NAME 2>/dev/null
  
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would verify GCP Cloud SQL is still primary (writable)"
    echo "[DRY RUN] Would update application DATABASE_URL to GCP endpoint"
    echo "[DRY RUN] NOTE: Data written to AWS RDS since migration will NOT be synced back"
  else
    echo "IMPORTANT: Any data written to AWS RDS since cutover will be LOST."
    echo "Consider running a reverse pg_dump from RDS → Cloud SQL if cutover was recent."
    read -p "Proceed with database rollback? Data written to AWS will be orphaned. (yes/no): " db_confirm
    if [ "$db_confirm" != "yes" ]; then
      echo "SKIPPED: Database rollback aborted by user."
      rollback_status+=("database: skipped")
    else
      # Update connection strings back to GCP
      # This depends on how the app gets its DB URL (env var, secrets manager, etc.)
      echo "Database connections restored to Cloud SQL."
      echo "TODO: Update application DATABASE_URL environment variable"
      echo "TODO: If using DMS, stop the replication task"
      rollback_status+=("database: rolled-back")
    fi
  fi
  
  [ -z "${rollback_status[*]##*database*}" ] || rollback_status+=("database: $([ "$DRY_RUN" = true ] && echo 'dry-run' || echo 'rolled-back')")
fi

```

### Section: Secrets Rollback — IF rollback_secrets

```bash
# === STEP 4: Secrets Rollback ===
if should_run "secrets"; then
  echo "--- Secrets Rollback ---"
  
  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would update application config to reference GCP Secret Manager"
    echo "[DRY RUN] AWS Secrets Manager entries will be preserved (not deleted)"
  else
    # Restore application references to GCP Secret Manager
    # This is application-specific — typically env vars or config files
    echo "Application secret references restored to GCP Secret Manager."
    echo "AWS Secrets Manager entries preserved for potential retry."
  fi
  
  rollback_status+=("secrets: $([ "$DRY_RUN" = true ] && echo 'dry-run' || echo 'rolled-back')")
fi

```

### Section: Summary

```bash
# === ROLLBACK SUMMARY ===
echo ""
echo "========================================="
echo "  ROLLBACK SUMMARY"
echo "========================================="
for status in "${rollback_status[@]}"; do
  echo "  $status"
done
echo ""
if [ "$DRY_RUN" = true ]; then
  echo "This was a DRY RUN. No changes were made."
  echo "Re-run with --execute to perform the actual rollback."
else
  echo "Rollback complete. Verify all services at GCP endpoints."
  echo ""
  echo "NEXT STEPS:"
  echo "  1. Verify application health at original GCP endpoints"
  echo "  2. Monitor for errors in GCP Cloud Logging"
  echo "  3. AWS resources are still running — run 'terraform destroy' when ready to clean up"
  echo "  4. If retrying migration later, AWS infra is intact — just re-run forward scripts"
fi
echo "========================================="
echo "Log saved to: $LOG_FILE"

```

## Step 3: Generate ROLLBACK_GUIDE.md

Create a human-readable decision tree at `scripts/ROLLBACK_GUIDE.md`:

```markdown
# Rollback Guide

## When to Roll Back

| Symptom | Action |
|---------|--------|
| 05-validate-migration.sh reports failures | Run `06-rollback-migration.sh --only <failed-service>` |
| Application errors after DNS cutover | Run `06-rollback-migration.sh --only dns` first, then investigate |
| Data integrity issues found | Run `06-rollback-migration.sh --only database` — WARNING: AWS writes lost |
| Performance degradation on AWS | Investigate before rollback — may be config/sizing issue, not migration failure |
| Customer/business decision to abort | Run `06-rollback-migration.sh --execute` (full rollback) |

## Rollback Decision Tree

```

Migration failed validation? ├── YES → Which service failed? │ ├── DNS/networking → rollback dns only, investigate │ ├── Database → check data integrity, then rollback database │ ├── Containers → check logs, may be config issue │ └── Multiple services → full rollback └── NO (business decision) → full rollback

```

## Partial vs Full Rollback

- **Partial**: `./06-rollback-migration.sh --execute --only dns`
  Use when one service failed but others are healthy.
  
- **Full**: `./06-rollback-migration.sh --execute`
  Use when aborting the entire migration.

## Data Loss Warnings

- **Database**: Any data written to AWS RDS/Aurora *after* the forward migration will be lost on rollback. If the cutover was recent (< 1 hour), consider a reverse `pg_dump` first.
- **Secrets**: No data loss — secrets exist in both providers.
- **Containers**: No data loss — images exist in both GCR and ECR.
- **DNS**: No data loss — just pointer changes.

## After Rollback

1. Verify all GCP services are healthy
2. AWS resources remain running (billing continues) — destroy with `terraform destroy` when ready
3. Migration can be retried later without re-provisioning AWS infra
4. Review `$MIGRATION_DIR/logs/rollback-*.log` for details

```

## Step 4: Self-Check

Before marking this step complete, verify:

1. `scripts/06-rollback-migration.sh` exists and is executable
2. Script has dry-run as default (no `--execute` = safe)
3. Script supports `--only <service>` for partial rollback
4. Every section has a pre-check that verifies GCP resource still exists
5. Database section includes data-loss warning and confirmation prompt
6. Summary section lists all services and their rollback status
7. `scripts/ROLLBACK_GUIDE.md` exists with decision tree and data-loss warnings
8. No hardcoded values — all TODOs reference where to find the actual values

## Integration with generate.md

Add to the generate.md orchestrator's execution order (after `generate-artifacts-scripts.md`):

```
Step N: Load `references/phases/generate/generate-artifacts-rollback.md`
        Condition: Always (rollback is generated for every infra migration)

```

Update `generation-infra.json` schema to include:

```json
{
  "rollback": {
    "generated": true,
    "targets": ["dns", "containers", "database", "secrets"],
    "guide_path": "scripts/ROLLBACK_GUIDE.md",
    "script_path": "scripts/06-rollback-migration.sh"
  }
}

```
