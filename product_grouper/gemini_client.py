"""
Gemini API Client for Product Attribute Extraction

Handles communication with Google Gemini API including:
- Batch processing of product titles
- Response caching
- Rate limiting and retry logic
- Token counting and cost estimation
"""

import json
import time
import logging
from typing import List, Dict, Optional
from pathlib import Path

import google.generativeai as genai
from tqdm import tqdm


logger = logging.getLogger(__name__)


EXTRACTION_PROMPT_TEMPLATE = """You are a product classification expert for furniture and bedding products from Ripley Peru.

Analyze these product titles and extract structured attributes.

RULES:
1. Brand: Company name (RIZZOLI, ROSEN, PARAÍSO, etc.)
2. Product Type: Full category name (DORMITORIO AMERICANO, CAMA DIVÁN, COLCHÓN, DORMITORIO BOXET, DORMITORIO EUROPEO, CAMA EUROPEA, CAMA AMERICANA, DORMITORIO DIVÁN)
3. Base Model: Collection name shared across variants (VESUBIO, ROYAL CLOUD, REST, TEMPO, etc.)
   - Do NOT include size, color, or accessories in base model
   - Example: "DORMITORIO AMERICANO RIZZOLI VESUBIO 2 PLAZAS" → base_model = "VESUBIO"
4. Variant Attributes:
   - size: 1.5 PLAZAS, 2 PLAZAS, QUEEN, KING (exact text from title)
   - color: GRIS, AZUL, CHOCOLATE, ISSEY, GRAFITO, CHAMPAGNE, NIEBLA, etc.
   - accessories: Items after "+" or "CON" (CAJONES, VELADOR, ALMOHADAS, PROTECTOR, CABECERA)
   - features: Special attributes (BIPANEL, etc.)

IMPORTANT:
- Accessories and size are NOT part of base model
- If color is not explicitly mentioned, set to null
- Extract ALL accessories as separate list items
- Confidence score: 1.0 if certain, 0.5-0.9 if ambiguous, <0.5 if unclear

Products:
{products_json}

Return ONLY valid JSON array (no markdown, no explanation):
[
  {{
    "original_title": "...",
    "brand": "BRAND",
    "product_type": "FULL TYPE",
    "base_model": "MODEL",
    "variant_attributes": {{
      "size": "..." or null,
      "color": "..." or null,
      "accessories": ["...", "..."],
      "features": ["..."]
    }},
    "confidence": 0.95
  }}
]
"""


class GeminiClient:
    """Client for Google Gemini API with caching and rate limiting"""

    def __init__(
        self,
        api_key: str,
        cache_file: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
        temperature: float = 0.1,
        verbose: bool = True,
    ):
        """
        Initialize Gemini client

        Args:
            api_key: Google Gemini API key
            cache_file: Path to cache file for storing responses
            model_name: Gemini model to use
            temperature: Model temperature (lower = more deterministic)
            verbose: Enable progress bars and detailed logging
        """
        self.api_key = api_key
        self.cache_file = Path(cache_file) if cache_file else None
        self.model_name = model_name
        self.temperature = temperature
        self.verbose = verbose

        # Configure Gemini
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": temperature,
                "top_p": 0.95,
                "max_output_tokens": 16384,  # Increased for longer responses
                "response_mime_type": "application/json",
            },
        )

        # Load cache
        self.cache: Dict[str, Dict] = {}
        if self.cache_file and self.cache_file.exists():
            self._load_cache()

        # Stats
        self.total_api_calls = 0
        self.total_tokens_used = 0
        self.cache_hits = 0

    def extract_attributes_batch(
        self, products: List[Dict], batch_size: int = 25, delay: float = 4.5
    ) -> List[Dict]:
        """
        Extract attributes from products in batches

        Args:
            products: List of product dictionaries with 'title' field
            batch_size: Number of products per API call
            delay: Seconds to wait between batches (for rate limiting)

        Returns:
            List of products with extracted attributes added
        """
        results = []
        total_batches = (len(products) + batch_size - 1) // batch_size

        # Create progress bar if verbose
        pbar = tqdm(
            total=len(products),
            desc="Extracting attributes",
            disable=not self.verbose,
            unit="products",
        )

        for i in range(0, len(products), batch_size):
            batch = products[i : i + batch_size]
            batch_key = self._get_batch_cache_key(batch)

            # Check cache
            if batch_key in self.cache:
                logger.debug(f"Cache hit for batch {i // batch_size + 1}")
                extracted = self.cache[batch_key]
                self.cache_hits += 1
            else:
                # Call API
                logger.debug(
                    f"API call for batch {i // batch_size + 1}/{total_batches}"
                )
                extracted = self._extract_batch_api(batch)

                # Cache result
                self.cache[batch_key] = extracted
                self._save_cache()

                # Rate limiting (avoid 15 RPM limit)
                if i + batch_size < len(products):
                    time.sleep(delay)

            # Merge extracted attributes with original products
            for product, attrs in zip(batch, extracted):
                product_with_attrs = product.copy()
                product_with_attrs.update(attrs)
                results.append(product_with_attrs)

            pbar.update(len(batch))

        pbar.close()

        if self.verbose:
            logger.info(f"Extraction complete: {len(results)} products processed")
            logger.info(
                f"API calls: {self.total_api_calls}, Cache hits: {self.cache_hits}"
            )
            logger.info(f"Estimated tokens: ~{self.total_tokens_used}")

        return results

    def _extract_batch_api(self, batch: List[Dict]) -> List[Dict]:
        """Call Gemini API for a batch of products"""
        # Prepare product titles
        titles = [p["title"] for p in batch]
        products_json = json.dumps(titles, indent=2, ensure_ascii=False)

        # Create prompt
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(products_json=products_json)

        # Call API with retry
        response_text = self._call_api_with_retry(prompt, retries=3)

        # Parse response
        try:
            extracted = json.loads(response_text)
            if not isinstance(extracted, list) or len(extracted) != len(batch):
                logger.warning(
                    f"API returned {len(extracted)} results for {len(batch)} products"
                )
                # Pad or truncate if needed
                while len(extracted) < len(batch):
                    extracted.append(
                        self._create_fallback_attributes(batch[len(extracted)])
                    )
                extracted = extracted[: len(batch)]
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse API response: {e}")
            logger.error(f"Response text: {response_text[:500]}")
            # Return fallback for all products
            extracted = [self._create_fallback_attributes(p) for p in batch]

        return extracted

    def _call_api_with_retry(self, prompt: str, retries: int = 3) -> str:
        """Call Gemini API with exponential backoff retry"""
        last_error = None

        for attempt in range(retries):
            try:
                response = self.model.generate_content(prompt)
                self.total_api_calls += 1

                # Estimate tokens (rough: 1 token ≈ 4 chars)
                self.total_tokens_used += (len(prompt) + len(response.text)) // 4

                return response.text

            except Exception as e:
                last_error = e
                logger.warning(
                    f"API call failed (attempt {attempt + 1}/{retries}): {e}"
                )

                if attempt < retries - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)

        logger.error(f"All API retry attempts failed: {last_error}")
        raise last_error

    def _create_fallback_attributes(self, product: Dict) -> Dict:
        """Create fallback attributes when API fails"""
        title = product["title"]
        brand = product.get("brand", "UNKNOWN")

        return {
            "original_title": title,
            "brand": brand,
            "product_type": "UNKNOWN",
            "base_model": "UNKNOWN",
            "variant_attributes": {
                "size": None,
                "color": None,
                "accessories": [],
                "features": [],
            },
            "confidence": 0.0,
        }

    def _get_batch_cache_key(self, batch: List[Dict]) -> str:
        """Generate cache key for a batch"""
        titles = [p["title"] for p in batch]
        return json.dumps(titles, sort_keys=True)

    def _load_cache(self):
        """Load cache from file"""
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                self.cache = json.load(f)
            logger.info(f"Loaded cache with {len(self.cache)} entries")
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            self.cache = {}

    def _save_cache(self):
        """Save cache to file"""
        if not self.cache_file:
            return

        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def estimate_cost(self, num_products: int, batch_size: int = 25) -> Dict:
        """
        Estimate API cost for processing products

        Args:
            num_products: Number of products to process
            batch_size: Products per batch

        Returns:
            Dictionary with cost estimation details
        """
        num_batches = (num_products + batch_size - 1) // batch_size

        # Rough estimates for Gemini 1.5 Flash
        avg_input_tokens_per_batch = batch_size * 50  # ~50 tokens per product title
        avg_output_tokens_per_batch = (
            batch_size * 150
        )  # ~150 tokens per product response

        total_input_tokens = num_batches * avg_input_tokens_per_batch
        total_output_tokens = num_batches * avg_output_tokens_per_batch
        total_tokens = total_input_tokens + total_output_tokens

        # Gemini 1.5 Flash pricing (as of 2024)
        cost_per_million_input = 0.075  # $0.075 per 1M input tokens
        cost_per_million_output = 0.30  # $0.30 per 1M output tokens

        input_cost = (total_input_tokens / 1_000_000) * cost_per_million_input
        output_cost = (total_output_tokens / 1_000_000) * cost_per_million_output
        total_cost = input_cost + output_cost

        processing_time = num_batches * 6  # ~4.5s delay + ~1.5s API call

        return {
            "num_products": num_products,
            "num_batches": num_batches,
            "estimated_input_tokens": total_input_tokens,
            "estimated_output_tokens": total_output_tokens,
            "estimated_total_tokens": total_tokens,
            "estimated_cost_usd": round(total_cost, 4),
            "estimated_time_seconds": processing_time,
            "estimated_time_minutes": round(processing_time / 60, 1),
        }

    def get_stats(self) -> Dict:
        """Get current client statistics"""
        return {
            "total_api_calls": self.total_api_calls,
            "total_tokens_used": self.total_tokens_used,
            "cache_hits": self.cache_hits,
            "cache_size": len(self.cache),
            "estimated_cost_usd": round((self.total_tokens_used / 1_000_000) * 0.1, 4),
        }
