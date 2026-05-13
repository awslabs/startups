# Fixture: negative-services
#
# Purpose: Validate that forbidden AWS service recommendations never appear.
# Contains resources that trigger known "do not recommend" rules:
#   - Firebase Auth → must NOT map to Cognito (keep existing auth)
#   - BigQuery → must NOT map to Redshift/Athena/Glue/EMR (deferred only)
#   - Cloud Run → must NOT map to Lightsail or Elastic Beanstalk
#
# Resources:
#   PRIMARY:   google_cloud_run_v2_service, google_bigquery_dataset
#   SECONDARY: google_service_account, google_bigquery_table
#   EXCLUDED:  google_identity_platform_config (auth — skip entirely)

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
  project = "negative-test-project"
  region  = "us-central1"
}

# --- Auth resources (should be EXCLUDED from inventory entirely) ---

resource "google_identity_platform_config" "auth" {
  project = "negative-test-project"

  sign_in {
    allow_duplicate_emails = false

    email {
      enabled           = true
      password_required = true
    }
  }
}

resource "google_identity_platform_default_supported_idp_config" "google_sign_in" {
  project      = "negative-test-project"
  idp_id       = "google.com"
  client_id    = "placeholder.apps.googleusercontent.com"
  client_secret = "placeholder"

  enabled = true
}

# --- BigQuery (should map to Deferred, never Redshift/Athena/Glue/EMR) ---

resource "google_bigquery_dataset" "warehouse" {
  dataset_id = "data_warehouse"
  location   = "US"
}

resource "google_bigquery_table" "users" {
  dataset_id = google_bigquery_dataset.warehouse.dataset_id
  table_id   = "users"

  schema = jsonencode([
    { name = "user_id", type = "STRING", mode = "REQUIRED" },
    { name = "email", type = "STRING", mode = "REQUIRED" },
    { name = "created_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

# --- Cloud Run (should map to Fargate, never Lightsail/Beanstalk) ---

resource "google_cloud_run_v2_service" "api" {
  name     = "api-service"
  location = "us-central1"

  template {
    containers {
      image = "gcr.io/negative-test-project/api:latest"
    }

    service_account = google_service_account.api_sa.email
  }
}

resource "google_service_account" "api_sa" {
  account_id   = "api-sa"
  display_name = "API Service Account"
}
