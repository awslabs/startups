# Fixture: user-preferences
#
# Purpose: Validate that user-provided answers override defaults in
# preferences.json and influence Design output. Same infrastructure as
# minimal-cloud-run-sql but run with explicit user answers.
#
# The pre-seeded preferences.json has chosen_by: "user" entries.
# Invariants verify Design output reflects those choices (e.g., single-AZ
# when user picks "single-az", us-west-2 when user picks that region).
#
# Resources:
#   PRIMARY:   google_cloud_run_v2_service, google_sql_database_instance
#   SECONDARY: google_service_account

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
  project = "user-prefs-project"
  region  = "us-west1"
}

resource "google_cloud_run_v2_service" "api" {
  name     = "api-service"
  location = "us-west1"

  template {
    containers {
      image = "gcr.io/user-prefs-project/api:latest"

      env {
        name  = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_url.secret_id
            version = "latest"
          }
        }
      }
    }

    service_account = google_service_account.api_sa.email
  }
}

resource "google_sql_database_instance" "db" {
  name             = "main-db"
  database_version = "POSTGRES_15"
  region           = "us-west1"

  settings {
    tier = "db-f1-micro"

    ip_configuration {
      ipv4_enabled    = false
      private_network = "projects/user-prefs-project/global/networks/default"
    }
  }
}

resource "google_service_account" "api_sa" {
  account_id   = "api-sa"
  display_name = "API Service Account"
}

resource "google_secret_manager_secret" "db_url" {
  secret_id = "db-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url_v1" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = "placeholder"

  lifecycle {
    ignore_changes = [secret_data]
  }
}
