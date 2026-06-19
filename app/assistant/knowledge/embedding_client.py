import os
from typing import Any

import requests


class OllamaEmbeddingClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").replace("/v1", "")
        self.model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    def embed(self, text: str) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url.rstrip('/')}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
            embedding = payload.get("embedding")
            if not isinstance(embedding, list):
                raise ValueError("missing embedding")
            return {"error": False, "provider": "ollama", "model": self.model, "embedding": embedding}
        except Exception:
            return {
                "error": True,
                "provider": "ollama",
                "model": self.model,
                "message": "Das Embedding-Modell ist nicht installiert. Führe aus: ollama pull nomic-embed-text",
            }
