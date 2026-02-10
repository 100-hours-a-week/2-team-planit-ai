"""
Persona-Review Embedding Similarity Experiment

This module provides a modular framework for testing different combinations of:
- Persona generation prompts (P1-P3)
- Review formatting methods (R1-R4)
- Embedding models (E1-E4)

Usage:
    python run_experiment.py --config config/experiment_config.yaml
"""

from .core.experiment_runner import ExperimentRunner
from .core.data_loader import DataLoader
from .core.metrics import MetricsCalculator

__all__ = ["ExperimentRunner", "DataLoader", "MetricsCalculator"]
