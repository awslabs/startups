"""Chatbot API — uses OpenAI SDK for text generation and embeddings."""

import os

from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def generate_response(user_message: str, context: list[dict]) -> str:
    """Generate a chat response using GPT-4o."""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful customer support assistant."},
            *context,
            {"role": "user", "content": user_message},
        ],
        temperature=0.7,
        max_tokens=1024,
    )
    return response.choices[0].message.content


def get_embedding(text: str) -> list[float]:
    """Generate text embeddings for semantic search."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding
