"""
Experiment Runner for Persona-Review Similarity Experiments.

Updated to:
- Require LLM client for prompt experiments (no fallback)
- Use production PoiData directly for formatters
- Output similarity scores in results
- Support TravelPersonaAgent integration
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..registry.prompts import PROMPT_REGISTRY, PromptConfig
from ..registry.formatters import FORMATTER_REGISTRY, FormatterConfig
from ..registry.embedders import EMBEDDER_REGISTRY, create_embedder
from app.core.Agents.Poi.VectorDB.EmbeddingPipeline.BaseEmbeddingPipeline import EmbeddingTaskType
from .data_loader import DataLoader, PersonaData, ReviewData
from .metrics import MetricsCalculator, ExperimentMetrics

from app.core.models.PoiAgentDataclass.poi import PoiData
from app.core.LLMClient.VllmClient import VllmClient
from app.core.models.LlmClientDataclass.ChatMessageDataclass import ChatMessage, MessageData


logger = logging.getLogger(__name__)


@dataclass
class ExperimentConfig:
    """Configuration for an experiment run."""

    name: str
    personas_path: str
    reviews_path: str
    prompts: List[str]
    formatters: List[str]
    embedders: List[str]
    output_dir: str = "results"
    save_embeddings: bool = True
    # TODO: 고정값으로 박아넣음
    llm_client: Optional[Any] = VllmClient()

    @classmethod
    def from_yaml(cls, path: str) -> "ExperimentConfig":
        """Load configuration from YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        exp = data.get("experiment", {})
        datasets = data.get("datasets", {})
        variables = data.get("variables", {})
        output = data.get("output", {})

        return cls(
            name=exp.get("name", "unnamed_experiment"),
            personas_path=datasets.get("personas", ""),
            reviews_path=datasets.get("reviews", ""),
            prompts=variables.get("prompts", list(PROMPT_REGISTRY.keys())),
            formatters=variables.get("formatters", list(FORMATTER_REGISTRY.keys())),
            embedders=variables.get("embedders", list(EMBEDDER_REGISTRY.keys())),
            output_dir=output.get("results_dir", "results"),
            save_embeddings=output.get("save_embeddings", True),
        )


@dataclass
class SimilarityScore:
    """Individual similarity score between persona and POI."""
    persona_id: str
    poi_id: str
    similarity: float
    is_related: bool  # Ground truth


@dataclass
class ExperimentResult:
    """Result of a single experiment combination."""

    prompt_name: str
    formatter_name: str
    embedder_name: str
    metrics: ExperimentMetrics

    # Similarity details
    similarity_scores: List[SimilarityScore] = field(default_factory=list)

    # Generated content (optional)
    persona_embeddings: Optional[Dict[str, List[float]]] = None
    poi_embeddings: Optional[Dict[str, List[float]]] = None
    generated_personas: Optional[Dict[str, str]] = None
    formatted_reviews: Optional[Dict[str, str]] = None


@dataclass
class ExperimentResults:
    """Collection of all experiment results."""

    experiment_name: str
    timestamp: str
    config: Dict[str, Any]
    results: List[ExperimentResult] = field(default_factory=list)

    def best_combination(
        self, metric: str = "discrimination_score"
    ) -> Optional[ExperimentResult]:
        """Find the best combination based on a metric."""
        if not self.results:
            return None
        return max(self.results, key=lambda r: getattr(r.metrics, metric, 0))

    def to_dataframe(self):
        """Convert results to pandas DataFrame."""
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas required for to_dataframe()")

        rows = []
        for r in self.results:
            row = {
                "prompt": r.prompt_name,
                "formatter": r.formatter_name,
                "embedder": r.embedder_name,
                "avg_related_sim": r.metrics.avg_related_similarity,
                "avg_unrelated_sim": r.metrics.avg_unrelated_similarity,
                "discrimination": r.metrics.discrimination_score,
                "top_3_acc": r.metrics.top_3_accuracy,
                "top_5_acc": r.metrics.top_5_accuracy,
                "top_10_acc": r.metrics.top_10_accuracy,
            }
            rows.append(row)
        return pd.DataFrame(rows)

    def save(self, output_dir: str) -> str:
        """Save results to JSON file and markdown summary table."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        filename = f"{self.experiment_name}_{self.timestamp}.json"
        filepath = output_path / filename

        # Convert to serializable format with similarity scores
        data = {
            "experiment_name": self.experiment_name,
            "timestamp": self.timestamp,
            "config": self.config,
            "results": [
                {
                    "prompt": r.prompt_name,
                    "formatter": r.formatter_name,
                    "embedder": r.embedder_name,
                    "metrics": asdict(r.metrics),
                    "similarity_scores": [
                        {
                            "persona_id": s.persona_id,
                            "poi_id": s.poi_id,
                            "similarity": round(s.similarity, 4),
                            "is_related": s.is_related,
                        }
                        for s in r.similarity_scores[:100]  # Limit to top 100
                    ],
                    "generated_personas": dict(sorted(r.generated_personas.items())) if r.generated_personas else None,
                    "formatted_reviews": dict(sorted(r.formatted_reviews.items())) if r.formatted_reviews else None,
                }
                for r in self.results
            ],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Save markdown summary table
        md_filepath = self._save_markdown_summary(output_path)
        logger.info(f"Markdown summary saved to: {md_filepath}")

        return str(filepath)

    def _save_markdown_summary(self, output_path: Path) -> str:
        """Save experiment results as a markdown summary table."""
        md_filename = f"{self.experiment_name}_{self.timestamp}_summary.md"
        md_filepath = output_path / md_filename

        # Sort results by discrimination_score descending
        sorted_results = sorted(
            self.results,
            key=lambda r: (
                r.metrics.avg_related_similarity,
                r.metrics.avg_unrelated_similarity,
                r.metrics.top_3_accuracy,
                r.metrics.top_5_accuracy,
                r.metrics.top_10_accuracy,
                r.metrics.discrimination_score,
            ),
            reverse=True,
        )

        lines = [
            f"# Experiment Results: {self.experiment_name}",
            "",
            f"**Timestamp:** {self.timestamp}",
            "",
            "## Configuration",
            "",
            f"- **Prompts:** {', '.join(self.config.get('prompts', []))}",
            f"- **Formatters:** {', '.join(self.config.get('formatters', []))}",
            f"- **Embedders:** {', '.join(self.config.get('embedders', []))}",
            f"- **Num Personas:** {self.config.get('num_personas', 'N/A')}",
            f"- **Num POIs:** {self.config.get('num_pois', 'N/A')}",
            "",
            "## Results Summary",
            "",
            "| Prompt | Formatter | Embedder | Avg Related Sim | Avg Unrelated Sim | Std Related | Std Unrelated | Discrimination | Top-3 Acc | Top-5 Acc | Top-10 Acc |",
            "|--------|-----------|----------|-----------------|-------------------|-------------|---------------|----------------|-----------|-----------|------------|",
        ]

        for r in sorted_results:
            m = r.metrics
            lines.append(
                f"| {r.prompt_name} | {r.formatter_name} | {r.embedder_name} | "
                f"{m.avg_related_similarity:.4f} | {m.avg_unrelated_similarity:.4f} | "
                f"{m.std_related_similarity:.4f} | {m.std_unrelated_similarity:.4f} | "
                f"{m.discrimination_score:.4f} | {m.top_3_accuracy:.4f} | "
                f"{m.top_5_accuracy:.4f} | {m.top_10_accuracy:.4f} |"
            )

        # Add best combination highlight
        best = self.best_combination("discrimination_score")
        if best:
            lines.extend([
                "",
                "## Best Combination (by Discrimination Score)",
                "",
                f"- **Prompt:** {best.prompt_name}",
                f"- **Formatter:** {best.formatter_name}",
                f"- **Embedder:** {best.embedder_name}",
                f"- **Discrimination Score:** {best.metrics.discrimination_score:.4f}",
                f"- **Top-5 Accuracy:** {best.metrics.top_5_accuracy:.4f}",
            ])

        # Add Generated Content Reference
        lines.append("")
        lines.append("## Generated Content Reference")

        # Group by (prompt, formatter) to avoid duplication
        content_map = {}
        for r in self.results:
            key = (r.prompt_name, r.formatter_name)
            if key not in content_map:
                content_map[key] = r

        for prompt_name, formatter_name in sorted(content_map.keys()):
            r = content_map[(prompt_name, formatter_name)]
            
            lines.append("")
            lines.append(f"### Configuration: {prompt_name} + {formatter_name}")
            
            lines.append("")
            lines.append("#### Personas")
            if r.generated_personas:
                for pid, text in sorted(r.generated_personas.items()):
                    lines.append(f"- **{pid}**: {text.replace(chr(10), ' ')}")

            lines.append("")
            lines.append("#### Reviews")
            if r.formatted_reviews:
                for oid, text in sorted(r.formatted_reviews.items()):
                    lines.append(f"- **{oid}**: {text.replace(chr(10), ' ')}")

            lines.append("")
            lines.append("---")

        # Add Generated Content Reference
        lines.append("")
        lines.append("## Generated Content Reference")

        # Group by (prompt, formatter) to avoid duplication
        content_map = {}
        for r in self.results:
            key = (r.prompt_name, r.formatter_name)
            if key not in content_map:
                content_map[key] = r

        for prompt_name, formatter_name in sorted(content_map.keys()):
            r = content_map[(prompt_name, formatter_name)]
            
            lines.append("")
            lines.append(f"### Configuration: {prompt_name} + {formatter_name}")
            
            lines.append("")
            lines.append("#### Personas")
            if r.generated_personas:
                for pid, text in sorted(r.generated_personas.items()):
                    lines.append(f"- **{pid}**: {text.replace(chr(10), ' ')}")

            lines.append("")
            lines.append("#### Reviews")
            if r.formatted_reviews:
                for oid, text in sorted(r.formatted_reviews.items()):
                    lines.append(f"- **{oid}**: {text.replace(chr(10), ' ')}")

            lines.append("")
            lines.append("---")

        with open(md_filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return str(md_filepath)


class ExperimentRunner:
    """Run persona-review similarity experiments."""

    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.data_loader = DataLoader()
        self.metrics_calculator = MetricsCalculator()

        # Validate configuration
        self._validate_config()

        # Load data
        self.personas: List[PersonaData] = []
        self.reviews: Optional[ReviewData] = None

        # Cache for generated content
        self._persona_cache: Dict[Tuple[str, str], str] = {}
        self._review_cache: Dict[Tuple[str, str], str] = {}            

    def _validate_config(self) -> None:
        """Validate that all configured variables exist in registries."""
        for prompt in self.config.prompts:
            if prompt not in PROMPT_REGISTRY:
                raise ValueError(f"Unknown prompt: {prompt}. Available: {list(PROMPT_REGISTRY.keys())}")

        for formatter in self.config.formatters:
            if formatter not in FORMATTER_REGISTRY:
                raise ValueError(f"Unknown formatter: {formatter}. Available: {list(FORMATTER_REGISTRY.keys())}")

        for embedder in self.config.embedders:
            if embedder not in EMBEDDER_REGISTRY:
                raise ValueError(f"Unknown embedder: {embedder}. Available: {list(EMBEDDER_REGISTRY.keys())}")

    def load_data(self) -> None:
        """Load persona and review datasets."""
        logger.info(f"Loading personas from: {self.config.personas_path}")
        self.personas = self.data_loader.load_personas(self.config.personas_path)

        logger.info(f"Loading reviews from: {self.config.reviews_path}")
        self.reviews = self.data_loader.load_reviews(self.config.reviews_path)

        logger.info(f"Loaded {len(self.personas)} personas and {len(self.reviews.pois)} POIs")

    def generate_persona_text(
        self, persona: PersonaData, prompt_config: PromptConfig, qa_false: bool = False
    ) -> str:
        """Generate persona text using specified prompt. LLM client is required."""
        cache_key = (persona.id, prompt_config.name)
        if cache_key in self._persona_cache:
            return self._persona_cache[cache_key]

        if not self.config.llm_client:
            raise ValueError(
                "LLM client is required for prompt experiments. "
                "Set llm_client in ExperimentConfig or use --llm-client option."
            )

        # Generate using prompt template + llm_client.call_llm()
        prompt_text = prompt_config.generator(
            qa_items=persona.qa_items if not qa_false else [],
            itinerary_request=persona.itinerary_request,
        )
        
        messages: ChatMessage = ChatMessage(
            content=[
                MessageData(role="user", content=prompt_text)
            ]
        )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    result = pool.submit(
                        asyncio.run,
                        self.config.llm_client.call_llm(messages)
                    ).result()
            else:
                result = loop.run_until_complete(
                    self.config.llm_client.call_llm(messages)
                )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.config.llm_client.call_llm(messages)
            )

        try: 
            # Extract content inside <final_response> tags
            match = re.search(r"<final_response>(.*?)</final_response>", result, re.DOTALL)
            if match:
                result = match.group(1).strip()
        except Exception: 
            pass

        self._persona_cache[cache_key] = result
        return result

    def format_review_text(
        self, poi: PoiData, formatter_config: FormatterConfig
    ) -> str:
        """Format POI using specified formatter with production PoiData."""
        cache_key = (poi.id, formatter_config.name)
        if cache_key in self._review_cache:
            return self._review_cache[cache_key]

        if formatter_config.requires_llm:
            if self.config.llm_client:
                result = formatter_config.formatter(
                    poi,
                    llm_client=self.config.llm_client,
                )
            else:
                raise ValueError(
                    f"Formatter {formatter_config.name} requires LLM but no client provided. "
                    f"Set llm_client in ExperimentConfig or use --llm-client option."
                )
        else:
            result = formatter_config.formatter(poi)

        self._review_cache[cache_key] = result
        return result

    def run(self) -> ExperimentResults:
        """Run all experiment combinations."""
        self.load_data()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results = ExperimentResults(
            experiment_name=self.config.name,
            timestamp=timestamp,
            config={
                "prompts": self.config.prompts,
                "formatters": self.config.formatters,
                "embedders": self.config.embedders,
                "num_personas": len(self.personas),
                "num_pois": len(self.reviews.pois) if self.reviews else 0,
            },
        )

        total_combinations = (
            len(self.config.prompts)
            * len(self.config.formatters)
            * len(self.config.embedders)
        )
        logger.info(f"Running {total_combinations} experiment combinations")

        for i, (prompt_name, formatter_name, embedder_name) in enumerate(
            product(
                self.config.prompts,
                self.config.formatters,
                self.config.embedders,
            )
        ):
            logger.info(
                f"[{i+1}/{total_combinations}] "
                f"Prompt={prompt_name}, Formatter={formatter_name}, Embedder={embedder_name}"
            )

            result = self._run_single_combination(
                prompt_name, formatter_name, embedder_name
            )
            results.results.append(result)

        # Save results
        if self.config.output_dir:
            output_path = results.save(self.config.output_dir)
            logger.info(f"Results saved to: {output_path}")

        return results

    def _run_single_combination(
        self, prompt_name: str, formatter_name: str, embedder_name: str
    ) -> ExperimentResult:
        """Run a single experiment combination."""
        prompt_config = PROMPT_REGISTRY[prompt_name]
        formatter_config = FORMATTER_REGISTRY[formatter_name]
        embedder = create_embedder(embedder_name)
        embedder.load_model()

        # Generate persona texts and embeddings
        persona_texts: Dict[str, str] = {}
        persona_embeddings: Dict[str, List[float]] = {}

        for persona in self.personas:
            text = self.generate_persona_text(persona, prompt_config)
            persona_texts[persona.id] = text
            persona_embeddings[persona.id] = embedder.embed(text, EmbeddingTaskType.QUERY)

        # Format reviews and generate embeddings
        formatted_reviews: Dict[str, str] = {}
        poi_embeddings: Dict[str, List[float]] = {}

        for poi in self.reviews.pois:
            text = self.format_review_text(poi, formatter_config)
            formatted_reviews[poi.id] = text
            poi_embeddings[poi.id] = embedder.embed(text, EmbeddingTaskType.DOCUMENT)

        # Calculate all similarity scores
        similarity_scores: List[SimilarityScore] = []
        for persona in self.personas:
            persona_emb = persona_embeddings[persona.id]
            for poi in self.reviews.pois:
                poi_emb = poi_embeddings[poi.id]
                sim = self.metrics_calculator.cosine_similarity(persona_emb, poi_emb)
                is_related = poi.id in persona.related_poi_ids
                similarity_scores.append(SimilarityScore(
                    persona_id=persona.id,
                    poi_id=poi.id,
                    similarity=sim,
                    is_related=is_related,
                ))

        # Build persona labels for metrics
        persona_labels: Dict[str, Tuple[List[str], List[str]]] = {}
        for persona in self.personas:
            persona_labels[persona.id] = (
                persona.related_poi_ids,
                persona.unrelated_poi_ids,
            )

        # Calculate metrics
        metrics = self.metrics_calculator.compute_metrics(
            prompt_name=prompt_name,
            formatter_name=formatter_name,
            embedder_name=embedder_name,
            persona_embeddings=persona_embeddings,
            poi_embeddings=poi_embeddings,
            persona_labels=persona_labels,
        )

        return ExperimentResult(
            prompt_name=prompt_name,
            formatter_name=formatter_name,
            embedder_name=embedder_name,
            metrics=metrics,
            similarity_scores=similarity_scores,
            persona_embeddings=persona_embeddings if self.config.save_embeddings else None,
            poi_embeddings=poi_embeddings if self.config.save_embeddings else None,
            generated_personas=persona_texts,
            formatted_reviews=formatted_reviews,
        )
