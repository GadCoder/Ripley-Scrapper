"""
Product Grouper - Main Orchestrator

Coordinates the entire product grouping workflow:
1. Load products from JSON
2. Extract attributes using regex patterns
3. Build hierarchical structure
4. Save results
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict

from .regex_extractor import RegexExtractor
from .hierarchy_builder import HierarchyBuilder


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ProductGrouper:
    """Main orchestrator for product grouping workflow"""

    def __init__(
        self,
        verbose: bool = True,
        # Deprecated parameters kept for backward compatibility
        api_key: Optional[str] = None,
        cache_file: Optional[str] = None,
    ):
        """
        Initialize Product Grouper

        Args:
            verbose: Enable detailed logging and progress bars
            api_key: Deprecated - no longer needed (kept for backward compatibility)
            cache_file: Deprecated - no longer needed (kept for backward compatibility)
        """
        self.verbose = verbose

        # Log deprecation warnings if old params are used
        if api_key:
            logger.warning(
                "api_key parameter is deprecated. Regex extraction doesn't require an API key."
            )
        if cache_file:
            logger.warning(
                "cache_file parameter is deprecated. Regex extraction is instant and doesn't need caching."
            )

        # Initialize components
        self.extractor = RegexExtractor(verbose=verbose)
        self.hierarchy_builder = HierarchyBuilder(verbose=verbose)

        # Stats
        self.start_time = None
        self.end_time = None

    def group_products(
        self,
        input_file: str,
        output_file: Optional[str] = None,
        batch_size: int = 25,
        confidence_threshold: float = 0.7,
        dry_run: bool = False,
    ) -> Dict:
        """
        Execute complete grouping workflow

        Args:
            input_file: Path to input JSON file with scraped products
            output_file: Path to output JSON file (default: input_grouped.json)
            batch_size: Products per Gemini API call
            confidence_threshold: Minimum confidence for grouped products
            dry_run: If True, only estimate cost without API calls

        Returns:
            Hierarchical dictionary with grouped products
        """
        self.start_time = time.time()

        # Determine output file
        if not output_file:
            input_path = Path(input_file)
            output_file = str(input_path.parent / f"{input_path.stem}_grouped.json")

        if self.verbose:
            logger.info("=" * 60)
            logger.info("Product Grouping - Ripley Scraper")
            logger.info("=" * 60)
            logger.info(f"Input:  {input_file}")
            logger.info(f"Output: {output_file}")

        # Step 1: Load products
        if self.verbose:
            logger.info("\n[1/4] Loading products...")

        products = self._load_products(input_file)

        if self.verbose:
            logger.info(f"Loaded {len(products)} products")

        # Dry run: estimate cost and exit
        if dry_run:
            return self._dry_run_estimate(products, batch_size)

        # Step 2: Extract attributes using regex
        if self.verbose:
            logger.info("\n[2/4] Extracting attributes with regex...")

        products_with_attrs = self.extractor.extract_attributes_batch(products)

        # Step 3: Build hierarchy
        if self.verbose:
            logger.info("\n[3/4] Building hierarchy...")

        hierarchy = self.hierarchy_builder.build_hierarchy(
            products_with_attrs, confidence_threshold=confidence_threshold
        )

        # Add extraction stats to metadata
        extractor_stats = self.extractor.get_stats()
        hierarchy["metadata"].update(
            {
                "extraction_method": "regex",
                "successful_extractions": extractor_stats["successful_extractions"],
                "partial_extractions": extractor_stats["partial_extractions"],
                "failed_extractions": extractor_stats["failed_extractions"],
                "extraction_success_rate": extractor_stats["success_rate"],
            }
        )

        # Step 4: Save results
        if self.verbose:
            logger.info("\n[4/4] Saving results...")

        self._save_hierarchy(hierarchy, output_file)

        self.end_time = time.time()
        processing_time = self.end_time - self.start_time
        hierarchy["metadata"]["processing_time_seconds"] = round(processing_time, 1)

        # Print summary
        if self.verbose:
            self._print_summary(hierarchy)

        return hierarchy

    def _load_products(self, input_file: str) -> list:
        """Load products from JSON file"""
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                products = json.load(f)

            if not isinstance(products, list):
                raise ValueError("Input JSON must be a list of products")

            return products

        except Exception as e:
            logger.error(f"Failed to load input file: {e}")
            raise

    def _save_hierarchy(self, hierarchy: Dict, output_file: str):
        """Save hierarchy to JSON file"""
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(hierarchy, f, ensure_ascii=False, indent=2)

            if self.verbose:
                logger.info(f"Saved: {output_file}")

        except Exception as e:
            logger.error(f"Failed to save output file: {e}")
            raise

    def _dry_run_estimate(self, products: list, batch_size: int) -> Dict:
        """Perform dry run cost estimation"""
        estimate = self.extractor.estimate_cost(len(products), batch_size)

        if self.verbose:
            logger.info("\n" + "=" * 60)
            logger.info("DRY RUN - Estimation (Regex-based extraction)")
            logger.info("=" * 60)
            logger.info(f"Products:           {estimate['num_products']}")
            logger.info(
                f"Est. Time:          {estimate['estimated_time_minutes']} minutes"
            )
            logger.info(f"Est. Cost:          $0.00 USD (regex is free!)")
            logger.info("=" * 60)
            logger.info("\nNote: Regex extraction is instant and free")
            logger.info("Run without --dry-run to proceed with grouping")

        return estimate

    def _print_summary(self, hierarchy: Dict):
        """Print summary of grouping results"""
        metadata = hierarchy["metadata"]

        logger.info("\n" + "=" * 60)
        logger.info("Summary")
        logger.info("=" * 60)
        logger.info(f"Total Products:        {metadata['total_products']}")
        logger.info(
            f"Grouped Products:      {metadata['grouped_products']} "
            f"({metadata['grouped_products'] / metadata['total_products'] * 100:.1f}%)"
        )
        logger.info(
            f"Ungrouped Products:    {metadata['ungrouped_products']} "
            f"({metadata['ungrouped_products'] / metadata['total_products'] * 100:.1f}%)"
        )
        logger.info("")
        logger.info(f"Brands:                {metadata['total_brands']}")
        logger.info(f"Product Types:         {metadata['total_product_types']}")
        logger.info(f"Models:                {metadata['total_models']}")
        logger.info("")
        logger.info(f"Processing Time:       {metadata['processing_time_seconds']}s")
        logger.info(
            f"Extraction Method:     {metadata.get('extraction_method', 'regex')}"
        )
        logger.info(
            f"Success Rate:          {metadata.get('extraction_success_rate', 0)}%"
        )
        logger.info("=" * 60)
        logger.info("\nDone!")
