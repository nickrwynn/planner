from __future__ import annotations

import os
from abc import ABC, abstractmethod


class EmbeddingsProvider(ABC):
    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingsProvider(EmbeddingsProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]


class SentenceTransformersProvider(EmbeddingsProvider):
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed_query(self, text: str) -> list[float]:
        import numpy as np

        vec = self._model.encode([text], normalize_embeddings=True)[0]
        return vec.astype(np.float32).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        vecs = self._model.encode(texts, normalize_embeddings=True)
        return [v.astype(np.float32).tolist() for v in vecs]


def get_embeddings_provider() -> EmbeddingsProvider | None:
    provider = (os.getenv("EMBEDDINGS_PROVIDER") or "").lower().strip()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        model = os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small")
        return OpenAIEmbeddingsProvider(api_key=api_key, model=model)
    if provider in ("sentence-transformers", "sentence_transformers"):
        model = os.getenv("SENTENCE_TRANSFORMERS_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        return SentenceTransformersProvider(model_name=model)
    return None

