"""
Metrics Calculator for Experiment Evaluation.

Provides:
- Cosine similarity calculations
- Top-K accuracy
- Discrimination score (related vs unrelated POI separation)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import numpy as np


@dataclass
class ExperimentMetrics:
    """Metrics for a single experiment configuration."""

    prompt_name: str
    formatter_name: str
    embedder_name: str

    # Similarity scores
    avg_related_similarity: float = 0.0
    avg_unrelated_similarity: float = 0.0
    std_related_similarity: float = 0.0
    std_unrelated_similarity: float = 0.0

    # Discrimination
    discrimination_score: float = 0.0  # related - unrelated

    # Top-K accuracy
    top_3_accuracy: float = 0.0
    top_5_accuracy: float = 0.0
    top_10_accuracy: float = 0.0

    # Per-persona details (optional)
    per_persona_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)


class MetricsCalculator:
    """Calculate evaluation metrics for embedding similarity experiments."""

    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        a = np.array(vec1)
        b = np.array(vec2)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def calculate_similarity_stats(
        similarities: List[float],
    ) -> Tuple[float, float]:
        """Calculate mean and std of similarities."""
        if not similarities:
            return 0.0, 0.0
        return float(np.mean(similarities)), float(np.std(similarities))

    @staticmethod
    def top_k_accuracy(
        similarities: List[Tuple[str, float]],  # (poi_id, similarity)
        related_poi_ids: List[str],
        k: int,
    ) -> float:
        """
        Calculate Top-K accuracy.
        Returns: proportion of related POIs in top K results.
        """
        if not similarities or not related_poi_ids:
            return 0.0

        # Sort by similarity descending
        sorted_sims = sorted(similarities, key=lambda x: x[1], reverse=True)
        top_k_ids = [poi_id for poi_id, _ in sorted_sims[:k]]

        # Count related POIs in top K
        hits = sum(1 for poi_id in top_k_ids if poi_id in related_poi_ids)
        return hits / min(k, len(related_poi_ids))

    @staticmethod
    def discrimination_score(
        related_similarities: List[float],
        unrelated_similarities: List[float],
    ) -> float:
        """
        Calculate discrimination score.
        Higher is better - means better separation between related and unrelated.
        """
        if not related_similarities or not unrelated_similarities:
            return 0.0

        avg_related = np.mean(related_similarities)
        avg_unrelated = np.mean(unrelated_similarities)
        return float(avg_related - avg_unrelated)

    def compute_metrics(
        self,
        prompt_name: str,
        formatter_name: str,
        embedder_name: str,
        persona_embeddings: Dict[str, List[float]],  # persona_id -> embedding
        poi_embeddings: Dict[str, List[float]],  # poi_id -> embedding
        persona_labels: Dict[str, Tuple[List[str], List[str]]],  # persona_id -> (related, unrelated)
    ) -> ExperimentMetrics:
        """
        Compute all metrics for one experiment configuration.

        Args:
            prompt_name: Name of the prompt used
            formatter_name: Name of the formatter used
            embedder_name: Name of the embedder used
            persona_embeddings: Dict mapping persona_id to embedding
            poi_embeddings: Dict mapping poi_id to embedding
            persona_labels: Dict mapping persona_id to (related_poi_ids, unrelated_poi_ids)
        """
        all_related_sims = []
        all_unrelated_sims = []
        all_top_3 = []
        all_top_5 = []
        all_top_10 = []
        per_persona_scores = {}

        for persona_id, persona_emb in persona_embeddings.items():
            if persona_id not in persona_labels:
                continue

            related_ids, unrelated_ids = persona_labels[persona_id]

            # Calculate similarities for this persona
            related_sims = []
            unrelated_sims = []
            all_sims = []  # For top-k calculation

            for poi_id, poi_emb in poi_embeddings.items():
                sim = self.cosine_similarity(persona_emb, poi_emb)
                all_sims.append((poi_id, sim))

                if poi_id in related_ids:
                    related_sims.append(sim)
                elif poi_id in unrelated_ids:
                    unrelated_sims.append(sim)

            all_related_sims.extend(related_sims)
            all_unrelated_sims.extend(unrelated_sims)

            # Top-K for this persona
            if all_sims and related_ids:
                all_top_3.append(self.top_k_accuracy(all_sims, related_ids, 3))
                all_top_5.append(self.top_k_accuracy(all_sims, related_ids, 5))
                all_top_10.append(self.top_k_accuracy(all_sims, related_ids, 10))

            # Store per-persona scores
            per_persona_scores[persona_id] = {
                "avg_related": float(np.mean(related_sims)) if related_sims else 0.0,
                "avg_unrelated": float(np.mean(unrelated_sims)) if unrelated_sims else 0.0,
                "discrimination": self.discrimination_score(related_sims, unrelated_sims),
            }

        # Aggregate metrics
        avg_related, std_related = self.calculate_similarity_stats(all_related_sims)
        avg_unrelated, std_unrelated = self.calculate_similarity_stats(all_unrelated_sims)

        return ExperimentMetrics(
            prompt_name=prompt_name,
            formatter_name=formatter_name,
            embedder_name=embedder_name,
            avg_related_similarity=avg_related,
            avg_unrelated_similarity=avg_unrelated,
            std_related_similarity=std_related,
            std_unrelated_similarity=std_unrelated,
            discrimination_score=self.discrimination_score(all_related_sims, all_unrelated_sims),
            top_3_accuracy=float(np.mean(all_top_3)) if all_top_3 else 0.0,
            top_5_accuracy=float(np.mean(all_top_5)) if all_top_5 else 0.0,
            top_10_accuracy=float(np.mean(all_top_10)) if all_top_10 else 0.0,
            per_persona_scores=per_persona_scores,
        )
