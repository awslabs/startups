terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "test-project"
  region  = "us-central1"
}

# PRIMARY: Compute (Cloud Run)
resource "google_cloud_run_v2_service" "api" {
  name     = "api-service"
  location = "us-central1"

  template {
    containers {
      image = "gcr.io/test-project/api:latest"
      env {
        name = "DATABASE_URL"
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

# PRIMARY: Database (Cloud SQL)
resource "google_sql_database_instance" "db" {
  name             = "app-db"
  database_version = "POSTGRES_15"
  region           = "us-central1"

  settings {
    tier = "db-f1-micro"
  }
}

# SECONDARY: Identity
resource "google_service_account" "api_sa" {
  account_id   = "api-service-account"
  display_name = "API Service Account"
}

# SECONDARY: Configuration (Secret)
resource "google_secret_manager_secret" "db_url" {
  secret_id = "database-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_url_v1" {
  secret      = google_secret_manager_secret.db_url.id
  secret_data = "postgresql://user:pass@${google_sql_database_instance.db.private_ip_address}:5432/app"
}
