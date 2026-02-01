"""
Product Grouper Package

Hierarchical product grouping using Google Gemini LLM.
Groups products by Brand -> Product Type -> Base Model -> Variants.
"""

from .grouper import ProductGrouper
from .gemini_client import GeminiClient
from .hierarchy_builder import HierarchyBuilder

__version__ = "0.1.0"
__all__ = ["ProductGrouper", "GeminiClient", "HierarchyBuilder"]
