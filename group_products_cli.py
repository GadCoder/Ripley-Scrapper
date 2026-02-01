#!/usr/bin/env python3
"""
Group Products CLI

Command-line interface for grouping Ripley products using AI.
Groups products hierarchically by Brand -> Type -> Model -> Variants.
"""

import argparse
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

from product_grouper import ProductGrouper


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Group Ripley products using Google Gemini AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python group_products_cli.py products.json
  
  # Custom output file
  python group_products_cli.py products.json --output grouped.json
  
  # Dry run (estimate cost only)
  python group_products_cli.py products.json --dry-run
  
  # Quiet mode
  python group_products_cli.py products.json --quiet
  
  # Custom API key
  python group_products_cli.py products.json --api-key YOUR_KEY
        """,
    )

    # Required arguments
    parser.add_argument("input_file", help="Input JSON file with scraped products")

    # Optional arguments
    parser.add_argument(
        "--output", "-o", help="Output JSON file (default: input_grouped.json)"
    )

    parser.add_argument(
        "--cache",
        default=".grouping_cache.json",
        help="Cache file path (default: .grouping_cache.json)",
    )

    parser.add_argument(
        "--batch-size", type=int, default=25, help="Products per API call (default: 25)"
    )

    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Minimum confidence for grouped products (default: 0.7)",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Estimate cost without making API calls"
    )

    parser.add_argument("--api-key", help="Gemini API key (overrides .env file)")

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output (default)"
    )

    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Get API key
    api_key = args.api_key or os.getenv("GEMINI_API_KEY")

    if not api_key:
        print("Error: GEMINI_API_KEY not found", file=sys.stderr)
        print("", file=sys.stderr)
        print("Please provide API key via:", file=sys.stderr)
        print("  1. --api-key argument", file=sys.stderr)
        print("  2. GEMINI_API_KEY environment variable", file=sys.stderr)
        print("  3. .env file with GEMINI_API_KEY=your_key", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "Get a free API key at: https://makersuite.google.com/app/apikey",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check input file exists
    if not Path(args.input_file).exists():
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    # Determine verbosity
    verbose = not args.quiet if not args.verbose else args.verbose

    try:
        # Initialize grouper
        grouper = ProductGrouper(
            api_key=api_key, cache_file=args.cache, verbose=verbose
        )

        # Run grouping
        hierarchy = grouper.group_products(
            input_file=args.input_file,
            output_file=args.output,
            batch_size=args.batch_size,
            confidence_threshold=args.confidence_threshold,
            dry_run=args.dry_run,
        )

        # Exit after dry run
        if args.dry_run:
            sys.exit(0)

        # Success
        if verbose:
            output_file = args.output or str(
                Path(args.input_file).parent
                / f"{Path(args.input_file).stem}_grouped.json"
            )
            print(f"\nOutput saved to: {output_file}")

        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        sys.exit(130)

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
