"""
Product Grouping Validator

Validates grouping quality and identifies potential issues.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class GroupingValidator:
    """Validates product grouping quality"""

    def __init__(self, gemini_client=None, verbose: bool = True):
        """
        Initialize validator

        Args:
            gemini_client: Optional GeminiClient for LLM-based validation
            verbose: Enable detailed logging
        """
        self.gemini_client = gemini_client
        self.verbose = verbose

    def validate_hierarchy(self, hierarchy: Dict, sample_rate: float = 0.2) -> Dict:
        """
        Validate hierarchy and identify potential issues

        Args:
            hierarchy: Hierarchical product structure
            sample_rate: Fraction of groups to validate (0.0-1.0)

        Returns:
            Validation results dictionary
        """
        issues = []

        # Check for single-variant models (might need regrouping)
        single_variant_models = self._find_single_variant_models(hierarchy)
        if single_variant_models:
            issues.append(
                {
                    "severity": "warning",
                    "type": "single_variant_model",
                    "count": len(single_variant_models),
                    "message": f"Found {len(single_variant_models)} models with only 1 variant",
                }
            )

        # Check for large price variance within models
        high_variance_models = self._find_high_price_variance(hierarchy)
        if high_variance_models:
            issues.append(
                {
                    "severity": "warning",
                    "type": "high_price_variance",
                    "count": len(high_variance_models),
                    "message": f"Found {len(high_variance_models)} models with >200% price variance",
                }
            )

        if self.verbose:
            logger.info(f"Validation found {len(issues)} issues")

        return {
            "validation_passed": len([i for i in issues if i["severity"] == "error"])
            == 0,
            "issues": issues,
            "single_variant_models": single_variant_models[:10],  # Top 10
            "high_variance_models": high_variance_models[:10],
        }

    def _find_single_variant_models(self, hierarchy: Dict) -> List[Dict]:
        """Find models with only 1 variant"""
        single_variant = []

        for brand in hierarchy.get("brands", []):
            for product_type in brand.get("product_types", []):
                for model in product_type.get("models", []):
                    if model.get("variant_count", 0) == 1:
                        single_variant.append(
                            {
                                "brand": brand["brand_name"],
                                "type": product_type["type_name"],
                                "model": model["base_model"],
                                "model_id": model["model_id"],
                            }
                        )

        return single_variant

    def _find_high_price_variance(self, hierarchy: Dict) -> List[Dict]:
        """Find models with unusually high price variance"""
        high_variance = []

        for brand in hierarchy.get("brands", []):
            for product_type in brand.get("product_types", []):
                for model in product_type.get("models", []):
                    price_range = model.get("price_range", {})

                    min_price = price_range.get("min_internet_price")
                    max_price = price_range.get("max_internet_price")

                    if min_price and max_price and min_price > 0:
                        variance_pct = ((max_price - min_price) / min_price) * 100

                        if variance_pct > 200:  # More than 200% difference
                            high_variance.append(
                                {
                                    "brand": brand["brand_name"],
                                    "type": product_type["type_name"],
                                    "model": model["base_model"],
                                    "model_id": model["model_id"],
                                    "variance_pct": round(variance_pct),
                                }
                            )

        return high_variance

    def generate_validation_report(self, validation_results: Dict) -> str:
        """Generate text report from validation results"""
        lines = ["=" * 60, "VALIDATION REPORT", "=" * 60, ""]

        if validation_results["validation_passed"]:
            lines.append("✓ Validation PASSED (no critical errors)")
        else:
            lines.append("✗ Validation FAILED (critical errors found)")

        lines.append("")
        lines.append(f"Total issues: {len(validation_results['issues'])}")
        lines.append("")

        for issue in validation_results["issues"]:
            severity_symbol = "⚠️" if issue["severity"] == "warning" else "❌"
            lines.append(f"{severity_symbol} {issue['message']}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)
