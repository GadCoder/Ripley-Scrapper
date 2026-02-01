"""
Product Analytics

Price analytics and statistics for grouped products.
"""

import logging
from typing import Dict, List
from collections import Counter

logger = logging.getLogger(__name__)


class ProductAnalytics:
    """Calculate analytics and statistics for product hierarchy"""

    def __init__(self, verbose: bool = True):
        """
        Initialize analytics

        Args:
            verbose: Enable detailed logging
        """
        self.verbose = verbose

    def generate_statistics_report(self, hierarchy: Dict) -> str:
        """
        Generate comprehensive statistics report

        Args:
            hierarchy: Hierarchical product structure

        Returns:
            Formatted text report
        """
        lines = ["=" * 60, "PRODUCT GROUPING STATISTICS REPORT", "=" * 60, ""]

        # Overview
        metadata = hierarchy.get("metadata", {})
        lines.append("📊 OVERVIEW")
        lines.append("-" * 60)
        lines.append(
            f"Total Products:              {metadata.get('total_products', 0)}"
        )
        lines.append(
            f"Grouped Products:            {metadata.get('grouped_products', 0)} "
            f"({self._percent(metadata.get('grouped_products', 0), metadata.get('total_products', 1))}%)"
        )
        lines.append(
            f"Ungrouped Products:          {metadata.get('ungrouped_products', 0)} "
            f"({self._percent(metadata.get('ungrouped_products', 0), metadata.get('total_products', 1))}%)"
        )
        lines.append("")
        lines.append(f"Brands:                      {metadata.get('total_brands', 0)}")
        lines.append(
            f"Product Types:               {metadata.get('total_product_types', 0)}"
        )
        lines.append(f"Base Models:                 {metadata.get('total_models', 0)}")

        if metadata.get("total_models", 0) > 0:
            avg_variants = metadata.get("grouped_products", 0) / metadata.get(
                "total_models", 1
            )
            lines.append(f"Avg Variants per Model:      {avg_variants:.1f}")

        lines.append("")
        lines.append(
            f"Processing Time:             {metadata.get('processing_time_seconds', 0):.2f}s"
        )
        lines.append(f"Extraction Method:           Regex-based (offline)")
        lines.append("")

        # Brands breakdown
        lines.append("=" * 60)
        lines.append("📦 BRANDS BREAKDOWN")
        lines.append("-" * 60)

        brands = hierarchy.get("brands", [])
        for brand in brands:
            price_range = brand.get("price_range", {})
            avg_price = price_range.get("avg_internet_price", 0)
            lines.append(
                f"{brand['brand_name']:20} {brand['product_count']:4} products  "
                f"{brand['model_count']:3} models  Avg: S/ {avg_price:,}"
            )

        lines.append("")

        # Product types
        lines.append("=" * 60)
        lines.append("🏷️  PRODUCT TYPES")
        lines.append("-" * 60)

        type_counts = Counter()
        for brand in brands:
            for ptype in brand.get("product_types", []):
                type_counts[ptype["type_name"]] += ptype["product_count"]

        for type_name, count in type_counts.most_common(10):
            pct = self._percent(count, metadata.get("grouped_products", 1))
            lines.append(f"{type_name:35} {count:4} products ({pct}%)")

        lines.append("")

        # Top deals
        lines.append("=" * 60)
        lines.append("💰 TOP 10 BEST DEALS (Highest Discount %)")
        lines.append("-" * 60)

        best_deals = self._find_best_deals(hierarchy, top_n=10)
        for i, deal in enumerate(best_deals, 1):
            lines.append(f"{i}. {deal['title'][:55]}")
            lines.append(
                f"   Normal: S/ {deal['normal_price']:,} → "
                f"Ripley: S/ {deal.get('ripley_price') or deal.get('internet_price'):,} "
                f"({deal['discount_percentage']}% off) - SKU: {deal['sku']}"
            )
            lines.append("")

        # Largest model families
        lines.append("=" * 60)
        lines.append("🔍 LARGEST MODEL FAMILIES (Most Variants)")
        lines.append("-" * 60)

        largest_models = self._find_largest_models(hierarchy, top_n=10)
        for i, model_info in enumerate(largest_models, 1):
            price_range = model_info["price_range"]
            lines.append(
                f"{i}. {model_info['brand']} {model_info['type']} - "
                f"{model_info['model']} ({model_info['variant_count']} variants)"
            )
            lines.append(
                f"   Price range: S/ {price_range.get('min_internet_price', 0):,} - "
                f"S/ {price_range.get('max_internet_price', 0):,}"
            )
            if model_info.get("sizes"):
                lines.append(f"   Sizes: {', '.join(model_info['sizes'])}")
            lines.append("")

        # Ungrouped products
        ungrouped = hierarchy.get("special_categories", {}).get("ungrouped", [])
        if ungrouped:
            lines.append("=" * 60)
            lines.append(f"⚠️  UNGROUPED PRODUCTS ({len(ungrouped)})")
            lines.append("-" * 60)
            for item in ungrouped[:10]:
                product = item.get("product", {})
                lines.append(f"- {product.get('title', 'Unknown')[:60]}")
                lines.append(f"  Reason: {item.get('reason', 'Unknown')}")
            if len(ungrouped) > 10:
                lines.append(f"... and {len(ungrouped) - 10} more")
            lines.append("")

        lines.append("=" * 60)
        lines.append(
            f"End of report - Generated: {metadata.get('processing_date', '')[:19]}"
        )
        lines.append("=" * 60)

        return "\n".join(lines)

    def _find_best_deals(self, hierarchy: Dict, top_n: int = 10) -> List[Dict]:
        """Find products with highest discount percentage"""
        all_products = []

        for brand in hierarchy.get("brands", []):
            for ptype in brand.get("product_types", []):
                for model in ptype.get("models", []):
                    for variant in model.get("variants", []):
                        if variant.get("discount_percentage"):
                            all_products.append(variant)

        # Sort by discount percentage
        sorted_products = sorted(
            all_products, key=lambda p: p.get("discount_percentage", 0), reverse=True
        )

        return sorted_products[:top_n]

    def _find_largest_models(self, hierarchy: Dict, top_n: int = 10) -> List[Dict]:
        """Find models with most variants"""
        all_models = []

        for brand in hierarchy.get("brands", []):
            for ptype in brand.get("product_types", []):
                for model in ptype.get("models", []):
                    all_models.append(
                        {
                            "brand": brand["brand_name"],
                            "type": ptype["type_name"],
                            "model": model["base_model"],
                            "variant_count": model.get("variant_count", 0),
                            "price_range": model.get("price_range", {}),
                            "sizes": model.get("available_sizes", []),
                        }
                    )

        # Sort by variant count
        sorted_models = sorted(
            all_models, key=lambda m: m["variant_count"], reverse=True
        )

        return sorted_models[:top_n]

    @staticmethod
    def _percent(value: int, total: int) -> str:
        """Calculate percentage as string"""
        if total == 0:
            return "0.0"
        return f"{(value / total * 100):.1f}"
