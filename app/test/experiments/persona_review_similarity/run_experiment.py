#!/usr/bin/env python
"""
CLI Entry Point for Persona-Review Similarity Experiments.

Usage:
    # Run with default config
    python run_experiment.py

    # Run with specific config
    python run_experiment.py --config config/quick_test_config.yaml

    # Run specific combinations
    python run_experiment.py --prompts P1_현재방식,P2_키워드중심 --embedders E1_MiniLM

    # Override data paths
    python run_experiment.py --personas data/personas/new_data.json
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.test.experiments.persona_review_similarity.core.experiment_runner import (
    ExperimentRunner,
    ExperimentConfig,
)
from app.test.experiments.persona_review_similarity.registry.prompts import list_prompts
from app.test.experiments.persona_review_similarity.registry.formatters import list_formatters
from app.test.experiments.persona_review_similarity.registry.embedders import list_embedders


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Persona-Review Embedding Similarity Experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_experiment.py
  python run_experiment.py --config config/quick_test_config.yaml
  python run_experiment.py --prompts P1_현재방식 --embedders E1_MiniLM,E3_KoSRoBERTa
  python run_experiment.py --list-variables
        """,
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/experiment_config.yaml",
        help="Path to experiment config YAML file",
    )

    parser.add_argument(
        "--prompts",
        type=str,
        help="Comma-separated list of prompts to use (overrides config)",
    )

    parser.add_argument(
        "--formatters",
        type=str,
        help="Comma-separated list of formatters to use (overrides config)",
    )

    parser.add_argument(
        "--embedders",
        type=str,
        help="Comma-separated list of embedders to use (overrides config)",
    )

    parser.add_argument(
        "--personas",
        type=str,
        help="Path to personas dataset (overrides config)",
    )

    parser.add_argument(
        "--reviews",
        type=str,
        help="Path to reviews dataset (overrides config)",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="Output directory for results (overrides config)",
    )

    parser.add_argument(
        "--name",
        type=str,
        help="Experiment name (overrides config)",
    )

    parser.add_argument(
        "--list-variables",
        action="store_true",
        help="List all available prompts, formatters, and embedders",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be run without executing",
    )

    return parser.parse_args()


def list_variables() -> None:
    """Print all available experiment variables."""
    print("\n=== Available Prompts ===")
    for name in list_prompts():
        print(f"  - {name}")

    print("\n=== Available Formatters ===")
    for name in list_formatters():
        print(f"  - {name}")

    print("\n=== Available Embedders ===")
    for name in list_embedders():
        print(f"  - {name}")

    print()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # List variables and exit
    if args.list_variables:
        list_variables()
        return 0

    # Resolve config path
    config_path = Path(__file__).parent / args.config
    if not config_path.exists():
        # Try absolute path
        config_path = Path(args.config)
        if not config_path.exists():
            logger.error(f"Config file not found: {args.config}")
            return 1

    logger.info(f"Loading config from: {config_path}")

    # Load config
    config = ExperimentConfig.from_yaml(str(config_path))



    # Apply command line overrides
    if args.prompts:
        config.prompts = [p.strip() for p in args.prompts.split(",")]
    if args.formatters:
        config.formatters = [f.strip() for f in args.formatters.split(",")]
    if args.embedders:
        config.embedders = [e.strip() for e in args.embedders.split(",")]
    if args.personas:
        config.personas_path = args.personas
    if args.reviews:
        config.reviews_path = args.reviews
    if args.output:
        config.output_dir = args.output
    if args.name:
        config.name = args.name

    # Calculate total combinations
    total = len(config.prompts) * len(config.formatters) * len(config.embedders)

    logger.info(f"Experiment: {config.name}")
    logger.info(f"Prompts: {config.prompts}")
    logger.info(f"Formatters: {config.formatters}")
    logger.info(f"Embedders: {config.embedders}")
    logger.info(f"Total combinations: {total}")

    if args.dry_run:
        logger.info("Dry run mode - not executing")
        return 0

    # Run experiment
    try:
        runner = ExperimentRunner(config)
        results = runner.run()

        # Print summary
        print("\n" + "=" * 60)
        print("EXPERIMENT RESULTS SUMMARY")
        print("=" * 60)

        best = results.best_combination("discrimination_score")
        if best:
            print(f"\nBest Combination (by discrimination score):")
            print(f"  Prompt:     {best.prompt_name}")
            print(f"  Formatter:  {best.formatter_name}")
            print(f"  Embedder:   {best.embedder_name}")
            print(f"  Discrimination Score: {best.metrics.discrimination_score:.4f}")
            print(f"  Top-5 Accuracy: {best.metrics.top_5_accuracy:.4f}")

        print("\nAll Results:")
        print("-" * 60)
        for r in sorted(results.results, key=lambda x: x.metrics.discrimination_score, reverse=True):
            print(
                f"  {r.prompt_name:15} | {r.formatter_name:12} | {r.embedder_name:20} | "
                f"disc={r.metrics.discrimination_score:.4f} | top5={r.metrics.top_5_accuracy:.4f}"
            )

        return 0

    except Exception as e:
        logger.exception(f"Experiment failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
