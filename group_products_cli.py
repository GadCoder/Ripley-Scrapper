#!/usr/bin/env python3
"""
Group Products CLI

Command-line interface for grouping Ripley products using regex-based extraction.
Groups products hierarchically by Brand -> Type -> Model -> Variants.
"""

import argparse
import sys
from pathlib import Path

from product_grouper import ProductGrouper


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Group Ripley products using regex-based attribute extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python group_products_cli.py products.json
  
  # Custom output file
  python group_products_cli.py products.json --output grouped.json
  
  # Dry run (preview only)
  python group_products_cli.py products.json --dry-run
  
  # Quiet mode
  python group_products_cli.py products.json --quiet
        """,
    )

    # Required arguments
    parser.add_argument("input_file", help="Input JSON file with scraped products")

    # Optional arguments
    parser.add_argument(
        "--output", "-o", help="Output JSON file (default: input_grouped.json)"
    )

    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.7,
        help="Minimum confidence for grouped products (default: 0.7)",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without processing"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output (default)"
    )

    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")

    args = parser.parse_args()

    # Check input file exists
    if not Path(args.input_file).exists():
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    # Determine verbosity
    verbose = not args.quiet if not args.verbose else args.verbose

    try:
        # Initialize grouper (no API key needed!)
        grouper = ProductGrouper(verbose=verbose)

        # Run grouping
        hierarchy = grouper.group_products(
            input_file=args.input_file,
            output_file=args.output,
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
