"""
Ripley API-based scraper that captures ALL 3 prices directly from the API.

This scraper extracts:
- normal_price (listPrice): Original/list price
- internet_price (offerPrice): Internet discount price
- ripley_price (cardPrice): Ripley card special price ⭐

Features:
- Pagination support to scrape all products in a category
- Rate limiting to avoid overwhelming the API
- Progress tracking for long scraping sessions
"""

import json
import logging
import requests
import time
import random
from datetime import datetime
from typing import List, Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RipleyAPIScraper:
    """
    Scraper that uses Ripley's internal API to get ALL product data including 3 prices.

    Optimized for overnight, unattended scraping with safe rate limiting.
    """

    # Rate limiting presets (delay, variation)
    RATE_PRESETS = {
        "safe": (3.0, 2.0),  # 3-5s delay - safest, recommended for overnight runs
        "balanced": (2.0, 1.0),  # 2-3s delay - good balance (default)
        "fast": (1.0, 0.5),  # 1-1.5s delay - faster but higher detection risk
    }

    def __init__(self, max_retries: int = 5, retry_backoff: float = 2.0):
        """
        Initialize the Ripley API scraper with retry logic.

        Args:
            max_retries: Maximum number of retry attempts for failed requests (default: 5, increased for reliability)
            retry_backoff: Backoff factor for exponential retry delay (default: 2.0, more conservative)
        """
        self.base_api_url = "https://simple.ripley.com.pe/api/v1/catalog-products"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://simple.ripley.com.pe/",
        }
        self.products = []
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

        # Configure session with retry logic
        self.session = self._create_session_with_retries()

    def _create_session_with_retries(self) -> requests.Session:
        """
        Create a requests session with automatic retry logic.

        Returns:
            Configured requests.Session object
        """
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=self.retry_backoff,
            status_forcelist=[
                429,
                500,
                502,
                503,
                504,
            ],  # Retry on these HTTP status codes
            allowed_methods=["GET", "POST"],
            raise_on_status=False,  # Don't raise exception, let us handle it
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def scrape_category(
        self,
        category: str,
        sort: str = "mdco",
        type_param: str = "catalog",
        delay: Optional[float] = None,
        delay_variation: Optional[float] = None,
        rate_preset: str = "balanced",
        deduplicate: bool = True,
        start_page: int = 1,
        checkpoint_file: Optional[str] = None,
        checkpoint_interval: int = 10,
        only_ripley: bool = True,
    ) -> List[Dict]:
        """
        Scrape a category using the API with pagination support.
        Always scrapes ALL pages in the category for complete data collection.

        Args:
            category: Category slug (e.g., 'dormitorio', 'tecnologia')
            sort: Sort parameter (default: 'mdco' for recommended)
            type_param: Type parameter (default: 'catalog')
            delay: Base delay in seconds between page requests (overrides rate_preset if provided)
            delay_variation: Random variation added to delay (overrides rate_preset if provided)
            rate_preset: Rate limiting preset - "safe" (3-5s), "balanced" (2-3s, default), "fast" (1-1.5s)
            deduplicate: Remove duplicate products by SKU (default: True)
            start_page: Page number to start from (for resume functionality, default: 1)
            checkpoint_file: File to save progress checkpoints (default: None)
            checkpoint_interval: Save checkpoint every N pages (default: 10)
            only_ripley: Filter to only include products sold by Ripley (default: True)

        Returns:
            List of product dictionaries with all 3 prices

        Note:
            This method always scrapes ALL available pages to ensure complete data collection.

            Rate presets for overnight scraping:
            - "safe": 3-5s delays (~7-10 min for 87 pages) - Recommended for twice-weekly runs
            - "balanced": 2-3s delays (~4-5 min for 87 pages) - Good default
            - "fast": 1-1.5s delays (~2-3 min for 87 pages) - Use with caution
        """
        # Apply rate preset if custom delays not provided
        if delay is None or delay_variation is None:
            preset_delay, preset_variation = self.RATE_PRESETS.get(
                rate_preset, self.RATE_PRESETS["balanced"]
            )
            if delay is None:
                delay = preset_delay
            if delay_variation is None:
                delay_variation = preset_variation

        logger.info(
            f"✓ Rate limit: {delay}s + random(0-{delay_variation}s) = {delay}-{delay + delay_variation}s per page"
        )
        url = f"{self.base_api_url}/{category}"
        all_products = []
        page = start_page

        if start_page > 1:
            logger.info(
                f"Resuming scrape of category: {category} from page {start_page}"
            )
        else:
            logger.info(f"Starting to scrape category: {category}")

        if only_ripley:
            logger.info(
                f"✓ Filter enabled: Only products sold by Ripley (excluding marketplace)"
            )
        else:
            logger.info(f"  Note: Including both Ripley and marketplace products")

        while True:
            params = {"s": sort, "type": type_param, "page": page}

            logger.info(f"Fetching page {page}...")

            try:
                response = self.session.post(
                    url, params=params, headers=self.headers, timeout=30
                )
                response.raise_for_status()

                data = response.json()
                products_data = data.get("products", [])
                pagination_info = data.get("pagination", {})

                if not products_data:
                    logger.info("No more products found")
                    break

                # Log pagination info on first page
                if page == 1:
                    total_pages = pagination_info.get("totalPages", "unknown")
                    total_results = pagination_info.get("totalResults", "unknown")
                    page_size = pagination_info.get("pageSize", len(products_data))

                    logger.info(f"✓ Total products in category: {total_results}")
                    logger.info(f"✓ Total pages: {total_pages}")
                    logger.info(f"✓ Products per page: {page_size}")

                    if isinstance(total_pages, int):
                        estimated_time = total_pages * (delay + delay_variation / 2)
                        estimated_minutes = estimated_time / 60
                        logger.info(
                            f"✓ Estimated scraping time: {estimated_minutes:.1f} minutes"
                        )

                    logger.info(
                        f"✓ Mode: Scraping ALL pages for complete data collection"
                    )

                # Extract products from this page
                page_products = []
                filtered_count = 0

                for product_data in products_data:
                    # Filter by seller if only_ripley is True
                    if only_ripley and product_data.get("isMarketplaceProduct", False):
                        filtered_count += 1
                        continue

                    product = self._extract_product(product_data, len(all_products) + 1)
                    if product:
                        page_products.append(product)

                all_products.extend(page_products)

                logger.info(
                    f"✓ Page {page}: Extracted {len(page_products)} products "
                    f"(Total so far: {len(all_products)})"
                )

                if filtered_count > 0 and only_ripley:
                    logger.info(
                        f"  ↳ Filtered out {filtered_count} marketplace products"
                    )

                # Save checkpoint if enabled
                if checkpoint_file and page % checkpoint_interval == 0:
                    self._save_checkpoint(checkpoint_file, category, page, all_products)
                    logger.info(f"✓ Checkpoint saved at page {page}")

                # Check if we should continue
                total_pages = pagination_info.get("totalPages", page)

                if page >= total_pages:
                    logger.info(f"✓ Reached last page ({page})")
                    break

                # Move to next page with randomized delay
                page += 1
                if delay > 0:
                    # Add random variation to delay to appear more human-like
                    actual_delay = delay + random.uniform(0, delay_variation)
                    logger.debug(f"  Sleeping for {actual_delay:.2f} seconds...")
                    time.sleep(actual_delay)

            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed on page {page}: {e}")
                break
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response on page {page}: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error on page {page}: {e}", exc_info=True)
                break

        # Deduplicate if requested
        if deduplicate and all_products:
            original_count = len(all_products)
            seen_skus = set()
            unique_products = []

            for product in all_products:
                sku = product.get("sku")
                if sku not in seen_skus:
                    seen_skus.add(sku)
                    # Re-assign IDs after deduplication
                    product["id"] = len(unique_products) + 1
                    unique_products.append(product)

            all_products = unique_products
            duplicates_removed = original_count - len(all_products)

            if duplicates_removed > 0:
                logger.info(f"✓ Removed {duplicates_removed} duplicate products")

        # Save final checkpoint if enabled
        if checkpoint_file and all_products:
            self._save_checkpoint(
                checkpoint_file, category, page, all_products, final=True
            )
            logger.info(f"✓ Final checkpoint saved")

        logger.info(
            f"✓ Scraping complete! Total products extracted: {len(all_products)}"
        )
        self.products = all_products
        return all_products

    def _save_checkpoint(
        self,
        checkpoint_file: str,
        category: str,
        last_page: int,
        products: List[Dict],
        final: bool = False,
    ):
        """
        Save a checkpoint of the scraping progress.

        Args:
            checkpoint_file: Path to checkpoint file
            category: Category being scraped
            last_page: Last successfully scraped page
            products: All products scraped so far
            final: Whether this is the final checkpoint
        """
        checkpoint_data = {
            "category": category,
            "last_page": last_page,
            "total_products": len(products),
            "products": products,
            "timestamp": datetime.now().isoformat(),
            "completed": final,
        }

        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_checkpoint(checkpoint_file: str) -> Dict:
        """
        Load a checkpoint file to resume scraping.

        Args:
            checkpoint_file: Path to checkpoint file

        Returns:
            Dictionary with checkpoint data including:
            - category: Category slug
            - last_page: Last scraped page number
            - products: Previously scraped products
            - completed: Whether scraping was completed
        """
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _extract_product(self, product_data: Dict, position: int) -> Optional[Dict]:
        """
        Extract product information from API response.

        Args:
            product_data: Raw product data from API
            position: Product position in the list

        Returns:
            Cleaned product dictionary
        """
        try:
            # Extract prices - THIS IS WHERE WE GET ALL 3 PRICES!
            prices = product_data.get("prices", {})

            product = {
                "id": position,
                "scraped_at": datetime.now().isoformat(),
                "sku": product_data.get("partNumber"),
                "title": product_data.get("name"),
                "brand": product_data.get("manufacturer"),
                "product_url": product_data.get("url"),
                "image_url": product_data.get("fullImage"),
                # ALL 3 PRICES FROM API!
                "normal_price": prices.get("listPrice"),  # Highest price (crossed out)
                "internet_price": prices.get("offerPrice"),  # Middle price (internet)
                "ripley_price": prices.get(
                    "cardPrice"
                ),  # Lowest price (Ripley card) ⭐
                # Additional price info
                "currency": "PEN",
                "discount_percentage": prices.get("discountPercentage"),
                "discount_amount": prices.get("discount"),
                "ripley_points": prices.get("ripleyPuntos"),
                # Product details
                "is_marketplace": product_data.get("isMarketplaceProduct", False),
                "is_available": not product_data.get("isUnavailable", False),
                "in_stock": not product_data.get("isOutOfStock", False),
            }

            return product

        except Exception as e:
            logger.warning(f"Failed to extract product {position}: {e}")
            return None

    def save_to_json(self, filename: str = None) -> str:
        """
        Save scraped products to JSON file.

        Args:
            filename: Output filename (default: ripley_products_api_TIMESTAMP.json)

        Returns:
            The filename used
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ripley_products_api_{timestamp}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.products, f, ensure_ascii=False, indent=2)

        logger.info(f"✓ Data saved to {filename}")
        return filename

    def print_summary(self):
        """Print a summary of scraped products."""
        if not self.products:
            logger.warning("No products to summarize")
            return

        total = len(self.products)
        with_3_prices = sum(
            1
            for p in self.products
            if p.get("normal_price")
            and p.get("internet_price")
            and p.get("ripley_price")
        )
        with_2_prices = sum(
            1
            for p in self.products
            if p.get("normal_price")
            and p.get("internet_price")
            and not p.get("ripley_price")
        )

        logger.info("\n" + "=" * 60)
        logger.info("SCRAPING SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total products: {total}")
        logger.info(f"Products with 3 prices: {with_3_prices} ✓")
        logger.info(f"Products with 2 prices: {with_2_prices}")

        if self.products:
            first = self.products[0]
            logger.info("\nFirst product sample:")
            logger.info(f"  Title: {first.get('title', '')[:60]}...")
            logger.info(f"  SKU: {first.get('sku')}")
            logger.info(f"  Normal Price: S/ {first.get('normal_price', 'N/A')}")
            logger.info(f"  Internet Price: S/ {first.get('internet_price', 'N/A')}")
            logger.info(
                f"  Ripley Card Price: S/ {first.get('ripley_price', 'N/A')} ⭐"
            )

            if first.get("ripley_price"):
                savings = first.get("normal_price", 0) - first.get("ripley_price", 0)
                logger.info(f"  💰 Total savings with Ripley card: S/ {savings}")

        logger.info("=" * 60)


def main():
    """Main function to demonstrate the API scraper with full pagination."""
    logger.info("=" * 60)
    logger.info("Ripley API Scraper - OVERNIGHT MODE")
    logger.info("ALL 3 PRICES | FULL CATEGORY SCRAPING | SAFE DELAYS")
    logger.info("=" * 60)

    scraper = RipleyAPIScraper()

    # Scrape dormitorio category - ALL pages
    category = "dormitorio"
    logger.info(f"\nScraping category: {category}")
    logger.info("Mode: OVERNIGHT - Scraping ALL available pages")
    logger.info("Delays: 2-3 seconds between pages for safe, undetected scraping")
    logger.info("Note: Only Ripley products (marketplace excluded)\n")

    # Scrape ALL pages with safe delays
    products = scraper.scrape_category(category)

    if products:
        # Save to JSON
        filename = scraper.save_to_json()

        # Print summary
        scraper.print_summary()

        logger.info(
            f"\n✓ SUCCESS! Saved {len(products)} Ripley products with ALL 3 PRICES to {filename}"
        )
        logger.info("✓ Complete category scraping finished successfully")
        logger.info("Tip: Run this twice a week for up-to-date product data")
        return 0
    else:
        logger.error("\n✗ Failed to scrape products")
        return 1


if __name__ == "__main__":
    exit(main())
