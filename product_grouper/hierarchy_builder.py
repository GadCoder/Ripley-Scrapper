"""
Hierarchy Builder

Builds hierarchical product structure:
Brand -> Product Type -> Base Model -> Variants

Includes analytics and metadata at each level.
"""

import re
import logging
from typing import List, Dict, Optional
from collections import defaultdict
from datetime import datetime


logger = logging.getLogger(__name__)


class HierarchyBuilder:
    """Builds hierarchical product grouping structure"""

    def __init__(self, verbose: bool = True):
        """
        Initialize hierarchy builder

        Args:
            verbose: Enable detailed logging
        """
        self.verbose = verbose

    def build_hierarchy(
        self, products_with_attributes: List[Dict], confidence_threshold: float = 0.7
    ) -> Dict:
        """
        Build hierarchical structure from products with extracted attributes

        Args:
            products_with_attributes: Products with extracted attributes from Gemini
            confidence_threshold: Minimum confidence to include in grouped (vs ungrouped)

        Returns:
            Hierarchical dictionary with brands, types, models, and variants
        """
        # Separate grouped and ungrouped products
        grouped_products, ungrouped_products = self._separate_by_confidence(
            products_with_attributes, confidence_threshold
        )

        if self.verbose:
            logger.info(f"Building hierarchy for {len(grouped_products)} products")
            logger.info(
                f"Ungrouped (low confidence): {len(ungrouped_products)} products"
            )

        # Build hierarchy
        hierarchy = {
            "brands": [],
            "special_categories": {"ungrouped": ungrouped_products},
            "metadata": {},
        }

        # Group by brand
        brands_dict = self._group_by_brand(grouped_products)

        # Process each brand
        for brand_name in sorted(brands_dict.keys()):
            brand_products = brands_dict[brand_name]
            brand_node = self._build_brand_node(brand_name, brand_products)
            hierarchy["brands"].append(brand_node)

        # Add metadata
        hierarchy["metadata"] = self._build_metadata(
            grouped_products, ungrouped_products, hierarchy["brands"]
        )

        if self.verbose:
            logger.info(
                f"Hierarchy built: {len(hierarchy['brands'])} brands, "
                f"{hierarchy['metadata']['total_models']} models"
            )

        return hierarchy

    def _separate_by_confidence(
        self, products: List[Dict], threshold: float
    ) -> tuple[List[Dict], List[Dict]]:
        """Separate products by confidence threshold"""
        grouped = []
        ungrouped = []

        for product in products:
            confidence = product.get("confidence", 1.0)

            if confidence >= threshold:
                grouped.append(product)
            else:
                ungrouped.append(
                    {
                        "reason": f"Low confidence ({confidence:.2f})",
                        "confidence_score": confidence,
                        "product": product,
                    }
                )

        return grouped, ungrouped

    def _group_by_brand(self, products: List[Dict]) -> Dict[str, List[Dict]]:
        """Group products by brand"""
        brands = defaultdict(list)

        for product in products:
            brand = product.get("brand", "UNKNOWN")
            brands[brand].append(product)

        return dict(brands)

    def _build_brand_node(self, brand_name: str, products: List[Dict]) -> Dict:
        """Build brand node with product types"""
        brand_id = self._slugify(brand_name)

        # Group by product type
        types_dict = defaultdict(list)
        for product in products:
            product_type = product.get("product_type", "UNKNOWN")
            types_dict[product_type].append(product)

        # Build type nodes
        product_types = []
        total_models = 0

        for type_name in sorted(types_dict.keys()):
            type_products = types_dict[type_name]
            type_node = self._build_type_node(brand_id, type_name, type_products)
            product_types.append(type_node)
            total_models += len(type_node["models"])

        # Calculate price range for brand
        price_range = self._calculate_price_range(products)

        return {
            "brand_name": brand_name,
            "brand_id": brand_id,
            "product_count": len(products),
            "model_count": total_models,
            "price_range": price_range,
            "product_types": product_types,
        }

    def _build_type_node(
        self, brand_id: str, type_name: str, products: List[Dict]
    ) -> Dict:
        """Build product type node with models"""
        type_id = self._slugify(type_name)

        # Group by base model
        models_dict = defaultdict(list)
        for product in products:
            base_model = product.get("base_model", "UNKNOWN")
            models_dict[base_model].append(product)

        # Build model nodes
        models = []
        for model_name in sorted(models_dict.keys()):
            model_products = models_dict[model_name]
            model_node = self._build_model_node(
                brand_id, type_id, model_name, model_products
            )
            models.append(model_node)

        return {
            "type_name": type_name,
            "type_id": type_id,
            "product_count": len(products),
            "model_count": len(models),
            "models": models,
        }

    def _build_model_node(
        self, brand_id: str, type_id: str, model_name: str, products: List[Dict]
    ) -> Dict:
        """Build model node with variants"""
        model_id = f"{brand_id}-{type_id}-{self._slugify(model_name)}"

        # Build variants
        variants = []
        for product in products:
            variant = self._build_variant(model_id, product)
            variants.append(variant)

        # Calculate model-level analytics
        price_range = self._calculate_price_range(products)

        # Extract available attributes
        available_sizes = self._extract_unique_values(
            products, ["variant_attributes", "size"]
        )
        available_colors = self._extract_unique_values(
            products, ["variant_attributes", "color"]
        )
        common_accessories = self._extract_common_accessories(products)

        return {
            "model_id": model_id,
            "base_model": model_name,
            "variant_count": len(variants),
            "price_range": price_range,
            "available_sizes": available_sizes,
            "available_colors": available_colors,
            "common_accessories": common_accessories,
            "variants": variants,
        }

    def _build_variant(self, model_id: str, product: Dict) -> Dict:
        """Build variant from product"""
        # Generate variant ID
        variant_attrs = product.get("variant_attributes", {})
        size = variant_attrs.get("size", "")
        color = variant_attrs.get("color", "")

        variant_id_parts = [model_id]
        if size:
            variant_id_parts.append(self._slugify(size))
        if color:
            variant_id_parts.append(self._slugify(color))

        variant_id = "-".join(variant_id_parts)

        # Build variant dict (include all original product fields)
        variant = product.copy()
        variant["variant_id"] = variant_id

        return variant

    def _calculate_price_range(self, products: List[Dict]) -> Dict:
        """Calculate price range statistics"""
        normal_prices = [
            p.get("normal_price") for p in products if p.get("normal_price")
        ]
        internet_prices = [
            p.get("internet_price") for p in products if p.get("internet_price")
        ]
        ripley_prices = [
            p.get("ripley_price") for p in products if p.get("ripley_price")
        ]

        result = {}

        if normal_prices:
            result["min_normal_price"] = min(normal_prices)
            result["max_normal_price"] = max(normal_prices)
            result["avg_normal_price"] = round(sum(normal_prices) / len(normal_prices))

        if internet_prices:
            result["min_internet_price"] = min(internet_prices)
            result["max_internet_price"] = max(internet_prices)
            result["avg_internet_price"] = round(
                sum(internet_prices) / len(internet_prices)
            )

        if ripley_prices:
            result["min_ripley_price"] = min(ripley_prices)
            result["max_ripley_price"] = max(ripley_prices)
            result["avg_ripley_price"] = round(sum(ripley_prices) / len(ripley_prices))

        return result

    def _extract_unique_values(
        self, products: List[Dict], path: List[str]
    ) -> List[str]:
        """Extract unique non-null values from nested dictionary path"""
        values = set()

        for product in products:
            value = product
            for key in path:
                value = value.get(key, {}) if isinstance(value, dict) else None
                if value is None:
                    break

            if value and isinstance(value, str):
                values.add(value)

        return sorted(list(values))

    def _extract_common_accessories(self, products: List[Dict]) -> List[str]:
        """Extract common accessories across products"""
        all_accessories = set()

        for product in products:
            variant_attrs = product.get("variant_attributes", {})
            accessories = variant_attrs.get("accessories", [])

            if isinstance(accessories, list):
                all_accessories.update(accessories)

        return sorted(list(all_accessories))

    def _build_metadata(
        self,
        grouped_products: List[Dict],
        ungrouped_products: List[Dict],
        brands: List[Dict],
    ) -> Dict:
        """Build metadata summary"""
        total_models = sum(brand["model_count"] for brand in brands)
        total_types = sum(len(brand["product_types"]) for brand in brands)

        return {
            "total_products": len(grouped_products) + len(ungrouped_products),
            "grouped_products": len(grouped_products),
            "ungrouped_products": len(ungrouped_products),
            "total_brands": len(brands),
            "total_product_types": total_types,
            "total_models": total_models,
            "processing_date": datetime.now().isoformat(),
        }

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert text to slug (lowercase, hyphenated)"""
        # Remove accents and convert to ASCII
        text = text.lower()
        # Replace spaces and special chars with hyphens
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        # Remove multiple hyphens
        text = re.sub(r"-+", "-", text)
        return text.strip("-")
