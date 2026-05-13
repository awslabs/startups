# Fixture: bigquery-specialist-gate
#
# Purpose: Validate the BigQuery specialist gate — google_bigquery_* resources
# must map to "Deferred — specialist engagement" in Design, be excluded from
# numeric cost totals in Estimate, and trigger the specialist advisory in Clarify.
#
# Resources:
#   PRIMARY:   google_bigquery_dataset, google_cloud_run_v2_service
#   SECONDARY: google_bigquery_table, google_service_account

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "analytics-project"
  region  = "us-central1"
}

# --- BigQuery Resources (should trigger specialist gate) ---

resource "google_bigquery_dataset" "analytics" {
  dataset_id = "analytics_warehouse"
  location   = "US"

  default_table_expiration_ms = 7776000000 # 90 days

  access {
    role          = "OWNER"
    user_by_email = "analytics-team@analytics-project.iam.gserviceaccount.com"
  }

  labels = {
    environment = "production"
    team        = "data-engineering"
  }
}

resource "google_bigquery_table" "events" {
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "raw_events"

  time_partitioning {
    type  = "DAY"
    field = "event_timestamp"
  }

  clustering = ["event_type", "user_id"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED" },
    { name = "event_type", type = "STRING", mode = "REQUIRED" },
    { name = "user_id", type = "STRING", mode = "NULLABLE" },
    { name = "event_timestamp", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "payload", type = "JSON", mode = "NULLABLE" }
  ])
}

resource "google_bigquery_table" "aggregates" {
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = "daily_aggregates"

  view {
    query          = "SELECT event_type, DATE(event_timestamp) as day, COUNT(*) as count FROM `analytics_warehouse.raw_events` GROUP BY 1, 2"
    use_legacy_sql = false
  }
}

# --- Cloud Run (non-BigQuery, should get normal mapping) ---

resource "google_cloud_run_v2_service" "ingest_api" {
  name     = "event-ingest-api"
  location = "us-central1"

  template {
    containers {
      image = "gcr.io/analytics-project/ingest-api:latest"

      env {
        name  = "BIGQUERY_DATASET"
        value = google_bigquery_dataset.analytics.dataset_id
      }
    }

    service_account = google_service_account.ingest_sa.email
  }
}

resource "google_service_account" "ingest_sa" {
  account_id   = "ingest-api-sa"
  display_name = "Event Ingest API Service Account"
}

resource "google_project_iam_member" "ingest_bq_writer" {
  project = "analytics-project"
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.ingest_sa.email}"
}
