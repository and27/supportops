import logging
import os
from typing import Protocol

import requests

from .logging_utils import log_event


class EmbeddingProvider(Protocol):
    model: str
    version: str | None

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str, version: str | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.version = version

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage", {})
        log_event(
            logging.INFO,
            "embedding_usage",
            model=self.model,
            input_count=len(texts),
            prompt_tokens=usage.get("prompt_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in data]


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = (os.getenv("EMBEDDING_PROVIDER") or "openai").lower()
    if provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        version = os.getenv("EMBEDDING_VERSION")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        return OpenAIEmbeddingProvider(api_key=api_key, model=model, version=version)

    raise RuntimeError(f"Unsupported embedding provider: {provider_name}")
