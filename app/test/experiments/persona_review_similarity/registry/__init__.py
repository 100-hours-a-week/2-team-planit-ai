"""
Registry module for experiment variables.

Each registry allows dynamic registration of:
- Prompts: Different persona generation strategies
- Formatters: Review text preprocessing methods
- Embedders: Embedding model configurations
"""

from .prompts import PROMPT_REGISTRY, register_prompt, PromptConfig
from .formatters import FORMATTER_REGISTRY, register_formatter, FormatterConfig
from .embedders import EMBEDDER_REGISTRY, register_embedder, EmbedderConfig

__all__ = [
    "PROMPT_REGISTRY",
    "register_prompt",
    "PromptConfig",
    "FORMATTER_REGISTRY",
    "register_formatter",
    "FormatterConfig",
    "EMBEDDER_REGISTRY",
    "register_embedder",
    "EmbedderConfig",
]
