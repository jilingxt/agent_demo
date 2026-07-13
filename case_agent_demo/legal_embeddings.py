from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

import numpy as np


def lexical_terms(text: str) -> list[str]:
    compact = re.sub(r"\s+", "", text.lower())
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", compact))
    terms = [chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))]
    terms.extend(re.findall(r"[a-z0-9_]{2,}", text.lower()))
    return list(dict.fromkeys(terms))


@dataclass
class HashingEmbeddingProvider:
    dimensions: int = 384
    model_name: str = "local-hashing-bigram-v1"
    backend: str = "hashing"
    semantic: bool = False

    def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(text)

    def _embed(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimensions, dtype=np.float32)
        for term in lexical_terms(text):
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector


@dataclass
class FastEmbedProvider:
    model_name: str = "BAAI/bge-small-zh-v1.5"
    cache_dir: str | None = None
    backend: str = "fastembed"
    semantic: bool = True
    dimensions: int = 512
    _model: object | None = field(default=None, init=False, repr=False)

    def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        model = self._get_model()
        return [self._normalize(item) for item in model.passage_embed(texts)]

    def embed_query(self, text: str) -> np.ndarray:
        model = self._get_model()
        return self._normalize(next(iter(model.query_embed(text))))

    def _get_model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:
                raise RuntimeError(
                    "语义向量需要安装 fastembed：pip install 'case-agent-demo[rag]'"
                ) from exc
            kwargs = {"model_name": self.model_name}
            if self.cache_dir:
                kwargs["cache_dir"] = self.cache_dir
            self._model = TextEmbedding(**kwargs)
        return self._model

    @staticmethod
    def _normalize(value: object) -> np.ndarray:
        vector = np.asarray(value, dtype=np.float32)
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0 or left.size != right.size:
        return 0.0
    denominator = math.sqrt(float(np.dot(left, left))) * math.sqrt(float(np.dot(right, right)))
    return float(np.dot(left, right) / denominator) if denominator else 0.0
