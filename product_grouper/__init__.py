"""
Product Grouper Package

Hierarchical product grouping using regex-based attribute extraction.
Groups products by Brand -> Product Type -> Base Model -> Variants.
"""

from .grouper import ProductGrouper
from .regex_extractor import RegexExtractor
from .hierarchy_builder import HierarchyBuilder

__version__ = "0.2.0"
__all__ = ["ProductGrouper", "RegexExtractor", "HierarchyBuilder"]
