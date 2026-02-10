"""
Embedder Registry for Embedding Models.

Register new embedders using the @register_embedder decorator:

    @register_embedder("E5_NewModel", "model-name-on-huggingface")
    class NewModelEmbedder(BaseExperimentEmbedder):
        ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Type
import numpy as np

from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import EmbeddingTaskType


@dataclass
class EmbedderConfig:
    """Configuration for an embedding model."""

    name: str
    model_name: str
    description: str
    dimension: int
    embedder_class: Type["BaseExperimentEmbedder"]


EMBEDDER_REGISTRY: Dict[str, EmbedderConfig] = {}


def register_embedder(
    name: str, model_name: str, description: str = "", dimension: int = 384
):
    """Decorator to register a new embedding model."""

    def decorator(cls: Type["BaseExperimentEmbedder"]):
        EMBEDDER_REGISTRY[name] = EmbedderConfig(
            name=name,
            model_name=model_name,
            description=description,
            dimension=dimension,
            embedder_class=cls,
        )
        return cls

    return decorator


class BaseExperimentEmbedder(ABC):
    """Abstract base class for experiment embedders."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None

    @abstractmethod
    def load_model(self) -> None:
        """Load the embedding model into memory."""
        pass

    @abstractmethod
    def embed(self, text: str, task_type: EmbeddingTaskType = EmbeddingTaskType.QUERY) -> List[float]:
        """Embed a single text string."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str], task_type: EmbeddingTaskType = EmbeddingTaskType.QUERY) -> List[List[float]]:
        """Embed multiple text strings."""
        pass

    def cosine_similarity(
        self, embedding1: List[float], embedding2: List[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings."""
        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ============================================================
# SentenceTransformer-based Embedders
# ============================================================
class SentenceTransformerEmbedder(BaseExperimentEmbedder):
    """Embedder using SentenceTransformers library."""

    def load_model(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)

    def embed(self, text: str, task_type: EmbeddingTaskType) -> List[float]:
        if self._model is None:
            self.load_model()
        return self._model.encode(text).tolist()

    def embed_batch(self, texts: List[str], task_type: EmbeddingTaskType) -> List[List[float]]:
        if self._model is None:
            self.load_model()
        embeddings = self._model.encode(texts)
        return [emb.tolist() for emb in embeddings]


# ============================================================
# E1: dragonkue/bge-m3-ko
# ============================================================
@register_embedder(
    name="E1_Dragonkue_BgeM3Ko",
    model_name="dragonkue/bge-m3-ko",
    description="1024차원",
    dimension=1024,
)
class DragonkueEmbedder(SentenceTransformerEmbedder):
    pass


# ============================================================
# E2: ibm-granite/granite-embedding-278m-multilingual
# ============================================================
@register_embedder(
    name="E2_IBM_Granite",
    model_name="ibm-granite/granite-embedding-278m-multilingual",
    description="다국어 지원, 768차원",
    dimension=768,
)
class GraniteEmbedder(SentenceTransformerEmbedder):
    pass


# ============================================================
# E3: ko-sroberta-multitask (한국어 특화)
# ============================================================
@register_embedder(
    name="E3_KoSRoBERTa",
    model_name="jhgan/ko-sroberta-multitask",
    description="한국어 특화, 768차원",
    dimension=768,
)
class KoSRoBERTaEmbedder(SentenceTransformerEmbedder):
    pass


# ============================================================
# E4: multilingual-e5-large (고성능 다국어)
# ============================================================
@register_embedder(
    name="E4_E5Large",
    model_name="intfloat/multilingual-e5-large",
    description="고성능 다국어, 1024차원",
    dimension=1024,
)
class E5LargeEmbedder(SentenceTransformerEmbedder):
    def _get_prefix(self, task_type: EmbeddingTaskType) -> str:
        if task_type == EmbeddingTaskType.DOCUMENT:
            return "passage: "
        return "query: "

    def embed(self, text: str, task_type: EmbeddingTaskType) -> List[float]:
        if self._model is None:
            self.load_model()
        prefix = self._get_prefix(task_type)
        return self._model.encode(f"{prefix}{text}").tolist()

    def embed_batch(self, texts: List[str], task_type: EmbeddingTaskType) -> List[List[float]]:
        if self._model is None:
            self.load_model()
        prefix = self._get_prefix(task_type)
        prefixed_texts = [f"{prefix}{t}" for t in texts]
        embeddings = self._model.encode(prefixed_texts)
        return [emb.tolist() for emb in embeddings]


def get_embedder(name: str) -> Optional[EmbedderConfig]:
    """Get a registered embedder configuration by name."""
    return EMBEDDER_REGISTRY.get(name)


def create_embedder(name: str) -> Optional[BaseExperimentEmbedder]:
    """Create an embedder instance by name."""
    config = get_embedder(name)
    if config is None:
        return None
    return config.embedder_class(config.model_name)


def list_embedders() -> List[str]:
    """List all registered embedder names."""
    return list(EMBEDDER_REGISTRY.keys())


# ============================================================
# E5: jina-embeddings-v3 (고성능 다국어)
# ============================================================
@register_embedder(
    name="E5_Jina",
    model_name="jinaai/jina-embeddings-v3",
    description="고성능 다국어, 1024차원",
    dimension=1024,
)
class JinaEmbedder(SentenceTransformerEmbedder):
    def load_model(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name, trust_remote_code=True)

    def _get_jina_task(self, task_type: EmbeddingTaskType) -> str:
        if task_type == EmbeddingTaskType.QUERY:
            return "retrieval.query"
        return "retrieval.passage"

    def embed(self, text: str, task_type: EmbeddingTaskType = EmbeddingTaskType.QUERY) -> List[float]:
        if self._model is None:
            self.load_model()
        jina_task = self._get_jina_task(task_type)
        embeddings = self._model.encode(
            [text],
            task=jina_task,
            prompt_name=jina_task,
        )
        return embeddings[0].tolist()

    def embed_batch(self, texts: List[str], task_type: EmbeddingTaskType = EmbeddingTaskType.QUERY) -> List[List[float]]:
        if self._model is None:
            self.load_model()
        jina_task = self._get_jina_task(task_type)
        embeddings = self._model.encode(
            texts,
            task=jina_task,
            prompt_name=jina_task,
        )
        return [emb[0].tolist() for emb in embeddings]

