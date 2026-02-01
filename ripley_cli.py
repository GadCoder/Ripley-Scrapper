#!/usr/bin/env python3
"""
Ripley Scraper CLI - Overnight scraping mode for complete data collection.

This tool is optimized for unattended, twice-weekly scraping runs.
It always scrapes ALL pages in each category for complete product data.

Examples:
    # Basic overnight scraping (safe delays, all pages)
    python ripley_cli.py dormitorio

    # Multiple categories with safe delays
    python ripley_cli.py dormitorio tecnologia electrohogar

    # Use balanced delays (faster, still safe)
    python ripley_cli.py dormitorio --rate balanced

    # With checkpoint saving every 10 pages
    python ripley_cli.py dormitorio --save-checkpoint

    # Resume from checkpoint
    python ripley_cli.py --resume checkpoint_dormitorio.json
"""

import argparse
import json
import sys
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
from api_scraper import RipleyAPIScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Scrape product data from Ripley Peru - OVERNIGHT MODE (always scrapes ALL pages)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s dormitorio
  %(prog)s tecnologia --rate safe
  %(prog)s dormitorio tecnologia --save-checkpoint
  %(prog)s --resume checkpoint_dormitorio.json
  
Rate Presets:
  safe     : 3-5s delays (~7-10 min/87 pages) - Recommended for overnight runs
  balanced : 2-3s delays (~4-5 min/87 pages) - Good default
  fast     : 1-1.5s delays (~2-3 min/87 pages) - Use with caution
        """,
    )

    parser.add_argument(
        "categories",
        nargs="*",  # Make optional (0 or more)
        help="Category slug(s) to scrape (e.g., dormitorio, tecnologia, electrohogar)",
    )

    parser.add_argument(
        "-o",
        "--output",
        help="Output filename (default: ripley_CATEGORY_TIMESTAMP.json)",
    )

    parser.add_argument(
        "--rate",
        choices=["safe", "balanced", "fast"],
        default="safe",
        help='Rate limiting preset: "safe" (3-5s, recommended), "balanced" (2-3s), "fast" (1-1.5s) - default: safe',
    )

    parser.add_argument(
        "-d",
        "--delay",
        type=float,
        help="Custom base delay in seconds (overrides --rate preset)",
    )

    parser.add_argument(
        "--delay-variation",
        type=float,
        help="Random delay variation in seconds (overrides --rate preset)",
    )

    parser.add_argument(
        "--no-deduplicate",
        action="store_true",
        help="Disable automatic deduplication of products",
    )

    parser.add_argument(
        "--include-marketplace",
        action="store_true",
        help="Include marketplace products (default: only Ripley products)",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum retry attempts for failed requests (default: 5)",
    )

    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=2.0,
        help="Backoff factor for exponential retry delay (default: 2.0)",
    )

    parser.add_argument(
        "--resume",
        help="Resume from checkpoint file",
    )

    parser.add_argument(
        "--save-checkpoint",
        action="store_true",
        help="Save progress checkpoint every 10 pages",
    )

    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress progress output"
    )

    parser.add_argument(
        "--combine",
        action="store_true",
        help="Combine multiple categories into single output file",
    )

    return parser.parse_args()


def scrape_category(
    scraper: RipleyAPIScraper,
    category: str,
    rate_preset: str,
    delay: Optional[float],
    delay_variation: Optional[float],
    deduplicate: bool,
    only_ripley: bool,
    output: Optional[str] = None,
    save_checkpoint: bool = False,
) -> list:
    """
    Scrape a single category (always ALL pages).

    Args:
        scraper: RipleyAPIScraper instance
        category: Category slug
        rate_preset: Rate limiting preset (safe/balanced/fast)
        delay: Custom delay override
        delay_variation: Custom delay variation override
        deduplicate: Whether to deduplicate
        only_ripley: Filter to only Ripley products
        output: Output filename
        save_checkpoint: Save progress checkpoints

    Returns:
        List of scraped products
    """
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Starting FULL scrape: {category}")
    logger.info(f"{'=' * 60}")

    # Prepare checkpoint filename if enabled
    checkpoint_file = None
    if save_checkpoint:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint_file = f"checkpoint_{category}_{timestamp}.json"
        logger.info(f"✓ Checkpoint saving enabled: {checkpoint_file}")

    products = scraper.scrape_category(
        category=category,
        rate_preset=rate_preset,
        delay=delay,
        delay_variation=delay_variation,
        deduplicate=deduplicate,
        only_ripley=only_ripley,
        checkpoint_file=checkpoint_file,
    )

    if products:
        # Save to file
        if output:
            filename = output
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ripley_{category}_{timestamp}.json"

        scraper.save_to_json(filename)
        scraper.print_summary()

        return products
    else:
        logger.error(f"Failed to scrape category: {category}")
        return []


def main():
    """Main CLI entry point."""
    args = parse_args()

    # Set logging level
    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    # Check if resuming from checkpoint
    if args.resume:
        if not Path(args.resume).exists():
            logger.error(f"Checkpoint file not found: {args.resume}")
            return 1

        logger.info(f"Resuming from checkpoint: {args.resume}")
        with open(args.resume, "r") as f:
            checkpoint = json.load(f)

        category = checkpoint.get("category")
        start_page = checkpoint.get("last_page", 1) + 1

        if not category:
            logger.error("Invalid checkpoint file: missing category")
            return 1

        logger.info(f"Resuming category '{category}' from page {start_page}")

        # Initialize scraper
        scraper = RipleyAPIScraper(
            max_retries=args.max_retries, retry_backoff=args.retry_backoff
        )

        # Resume scraping
        checkpoint_file = args.resume if args.save_checkpoint else None
        products = scraper.scrape_category(
            category=category,
            rate_preset=args.rate,
            delay=args.delay,
            delay_variation=args.delay_variation,
            deduplicate=not args.no_deduplicate,
            only_ripley=not args.include_marketplace,
            start_page=start_page,
            checkpoint_file=checkpoint_file,
        )

        if products:
            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = args.output or f"ripley_{category}_resumed_{timestamp}.json"
            scraper.save_to_json(filename)
            scraper.print_summary()
            return 0
        else:
            logger.error("Failed to resume scraping")
            return 1

    # Normal scraping mode
    if not args.categories:
        logger.error(
            "Error: No categories specified. Use --resume or provide category names."
        )
        return 1

    # Initialize scraper
    scraper = RipleyAPIScraper(
        max_retries=args.max_retries, retry_backoff=args.retry_backoff
    )

    # Display configuration
    logger.info(f"\n{'=' * 60}")
    logger.info("OVERNIGHT SCRAPING MODE - Configuration")
    logger.info(f"{'=' * 60}")
    logger.info(f"Rate preset: {args.rate}")
    if args.delay:
        logger.info(f"Custom delay: {args.delay}s (overrides preset)")
    if args.delay_variation:
        logger.info(
            f"Custom delay variation: {args.delay_variation}s (overrides preset)"
        )
    logger.info(f"Deduplication: {'ON' if not args.no_deduplicate else 'OFF'}")
    logger.info(
        f"Seller filter: {'Ripley only' if not args.include_marketplace else 'All sellers'}"
    )
    logger.info(f"Checkpoint saving: {'ON' if args.save_checkpoint else 'OFF'}")
    logger.info(f"Max retries: {args.max_retries}")
    logger.info(f"Categories: {', '.join(args.categories)}")
    logger.info(f"Note: ALL pages will be scraped (no page limit)")
    logger.info(f"{'=' * 60}\n")

    # Scrape categories
    all_products = []

    for category in args.categories:
        products = scrape_category(
            scraper=scraper,
            category=category,
            rate_preset=args.rate,
            delay=args.delay,
            delay_variation=args.delay_variation,
            deduplicate=not args.no_deduplicate,
            only_ripley=not args.include_marketplace,
            output=args.output if len(args.categories) == 1 else None,
            save_checkpoint=args.save_checkpoint,
        )

        all_products.extend(products)

        # Pause between categories
        if len(args.categories) > 1 and category != args.categories[-1]:
            logger.info("\n⏸️  Pausing 5 seconds before next category...\n")
            time.sleep(5)

    # If combining multiple categories, save to single file
    if args.combine and len(args.categories) > 1:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = args.output or f"ripley_combined_{timestamp}.json"

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Saving combined data: {filename}")
        logger.info(f"{'=' * 60}")

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(all_products, f, ensure_ascii=False, indent=2)

        logger.info(f"✓ Saved {len(all_products)} total products to {filename}")

    logger.info("\n✅ All scraping completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
