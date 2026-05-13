# Fixture: ai-workload-openai
#
# Purpose: Validate AI workload detection and model mapping.
# App code uses OpenAI SDK (not Vertex AI) hosted on GCP.
# Should trigger: ai-workload-profile.json creation, Category F questions
# in Clarify, Bedrock model mapping in Design, AI cost estimation.
#
# Resources:
#   PRIMARY:   google_cloud_run_v2_service (hosts the AI app)
#   SECONDARY: google_secret_manager_secret (OpenAI API key)

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
  project = "ai-chatbot-project"
  region  = "us-central1"
}

resource "google_cloud_run_v2_service" "chatbot" {
  name     = "chatbot-api"
  location = "us-central1"

  template {
    containers {
      image = "gcr.io/ai-chatbot-project/chatbot:latest"

      env {
        name  = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.openai_key.secret_id
            version = "latest"
          }
        }
      }

      env {
        name  = "MODEL_NAME"
        value = "gpt-4o"
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
    }

    service_account = google_service_account.chatbot_sa.email
  }
}

resource "google_service_account" "chatbot_sa" {
  account_id   = "chatbot-sa"
  display_name = "Chatbot Service Account"
}

resource "google_secret_manager_secret" "openai_key" {
  secret_id = "openai-api-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "openai_key_v1" {
  secret      = google_secret_manager_secret.openai_key.id
  secret_data = "placeholder"

  lifecycle {
    ignore_changes = [secret_data]
  }
}
