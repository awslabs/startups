"""Separate-modality and hosted-retrieval surfaces (static fixture).

These are intentionally separate capability paths so the recommendation flags
them as architectural work items: audio transcription, embeddings, and hosted
file search each need their own AWS target, not the primary text model.
"""

from openai import OpenAI


def _client():
    return OpenAI()


def transcribe(audio_file):
    """Audio modality — must map to a separate STT service (e.g. Transcribe)."""
    return _client().audio.transcriptions.create(model="whisper-1", file=audio_file)


def embed(text):
    """Embeddings — a separate Bedrock embedding model, not the text model."""
    return _client().embeddings.create(model="text-embedding-3-large", input=text)


def retrieve_docs(query, vector_store_id):
    """Hosted file search over a vector store — must re-platform onto retrieval."""
    return _client().responses.create(
        model="gpt-5.4",
        input=query,
        tools=[{"type": "file_search", "vector_store_ids": [vector_store_id]}],
    )
