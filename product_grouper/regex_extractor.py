"""
Regex-based Product Attribute Extractor

Extracts product attributes from titles using regex patterns instead of LLM.
This provides deterministic, instant, and free extraction.

Handles:
- Product categories (COLCHON, CAMA EUROPEA, BOXET, etc.)
- Sizes (1PLZ, 2PLZ, QUEEN, KING, etc.)
- Brands (ROSEN, PARAISO, DRIMER, etc.)
- Colors (auto-detected)
- Accessories (items after + or CON)
- Base model names
"""

import re
import logging
import unicodedata
from typing import List, Dict, Optional, Tuple

from tqdm import tqdm


logger = logging.getLogger(__name__)


# Product categories ordered by priority (longer matches first to avoid partial matches)
# These are the base categories - products may have prefixes like "DORMITORIO", "CAMA"
BASE_CATEGORIES = [
    # Multi-word categories (must match first)
    "CAMA EUROPEA",
    "CAMA CAJONES",
    "BOX TARIMA",
    "BOX SPRING",
    "BED BOXET",
    "BASE EUROPEA",
    "BASE BOX TARIMA",
    "BASE BOX EUROPEO",  # Added - variant of CAMA EUROPEA
    "BASE BOXET",
    "BASE CAJONES",
    "BASE DIVAN",
    "BASE AMERICANA",  # Added - maps to BOX TARIMA
    # Single-word categories
    "COLCHON",
    "CONJUNTO",  # Added - bundle type
    "DIVAN",
    "BOXET",
    "BERGERE",
    "RESPALDO",
    "VELADOR",
    "MESA",
    "POLTRONA",
    "BUTACA",
    "SOFA",
    "CABECERA",  # Added
    "ALMOHADA",  # Added
]

# Product type prefixes that combine with base categories
# e.g., "DORMITORIO BOXET", "CAMA EUROPEA"
TYPE_PREFIXES = [
    "DORMITORIO",
    "CAMA",
    "DOS COLCHONES",  # Special case for bundles
    "KIT",  # Added - for bundles like "KIT BASE CON CAJONES"
]

# Size patterns with their normalized form
# Order matters: more specific patterns first
SIZE_PATTERNS = [
    # 1.5 plaza variants - be more permissive
    (r"1[.,]5\s*PLAZAS?", "1.5PLZ"),
    (r"1[.,]5\s*PLZ", "1.5PLZ"),
    (r"1[.,]5PLZ", "1.5PLZ"),
    # 1 plaza variants
    (r"(?<![.,\d])1\s+PLAZAS?", "1PLZ"),
    (r"(?<![.,\d])1\s*PLAZA\b", "1PLZ"),
    (r"\b1PLZ\b", "1PLZ"),
    # 2 plaza variants
    (r"2\s*PLAZAS?", "2PLZ"),
    (r"\b2PLZ\b", "2PLZ"),
    # Queen/King
    (r"\bQUEEN\b", "QUEEN"),
    (r"\bKING\b", "KING"),
    # Cuerpos (for sofas, etc.)
    (r"3\s*CUERPOS?", "3C"),
    (r"\b3C\b", "3C"),
    (r"2\s*CUERPOS?", "2C"),
    (r"\b2C\b", "2C"),
    (r"1\s*CUERPOS?", "1C"),
    (r"\b1C\b", "1C"),
]

# Known brands with accent variations
BRANDS = [
    "ROSEN",
    "PARAISO",
    "PARAÍSO",
    "DRIMER",
    "SIMMONS",
    "SERTA",
    "DROM",
    "MICA",
    "FORLI",
    "FORLÍ",
    "RIZZOLI",
    "EL CISNE",
    "CISNE",  # Sometimes appears without "EL"
    # Additional brands found in data
    "RIPLEY HOME",
    "MAISON LINETT",
]

# Words that should NOT be considered as colors or model names
STOP_WORDS = {
    "CON",
    "DE",
    "Y",
    "EN",
    "LA",
    "EL",
    "LOS",
    "LAS",
    "UN",
    "UNA",
    "PARA",
    "POR",
    "SIN",
    "SOBRE",
    "BAJO",
    "ENTRE",
    "DESDE",
    "HASTA",
    "DORMITORIO",
    "CAMA",
    "COLCHON",
    "BASE",
    "BOX",
    "EUROPEO",
    "EUROPEA",
    "AMERICANO",
    "AMERICANA",
    "TARIMA",
    "SPRING",
    "DIVAN",
    "BOXET",
    "CAJONES",
    "CAJON",
    "CAJÓN",  # Added - with accent
    "BED",
    "KIT",  # Added - product type prefix
    "CONJUNTO",  # Added - product type
    "PLAZAS",
    "PLAZA",
    "PLZ",
    "QUEEN",
    "KING",
    "CUERPO",
    "CUERPOS",
    "ALMOHADA",
    "ALMOHADAS",
    "PROTECTOR",
    "CABECERA",
    "VELADOR",
    "VELADORES",  # Added - plural form
    "COMODA",
    "SOFA",
    "VISCOELASTICA",
    "VISCOELASTICAS",
    "SMART",
    "TV",
    "HD",
    "TELEVISOR",
}

# Common accessory patterns
ACCESSORY_PATTERNS = [
    r"\d+\s*ALMOHADAS?\s*(?:VISCOELASTICAS?)?",
    r"PROTECTOR",
    r"CABECERA",
    r"VELADOR(?:\s+\w+)?",
    r"COMODA",
    r"SOFA\s*CAMA(?:\s+\w+)?",
    r"BOX\s+TARIMA(?:\s+\w+)?",
    r"TELEVISOR.*",
    r"SMART\s+TV.*",
]


class RegexExtractor:
    """Regex-based product attribute extractor"""

    def __init__(self, verbose: bool = True):
        """
        Initialize the regex extractor

        Args:
            verbose: Enable progress bars and detailed logging
        """
        self.verbose = verbose

        # Pre-compile regex patterns for performance
        self._compile_patterns()

        # Stats
        self.total_processed = 0
        self.successful_extractions = 0
        self.partial_extractions = 0
        self.failed_extractions = 0

    def _compile_patterns(self):
        """Pre-compile all regex patterns for better performance"""
        # Compile size patterns
        self.size_patterns = [
            (re.compile(pattern, re.IGNORECASE), normalized)
            for pattern, normalized in SIZE_PATTERNS
        ]

        # Compile brand pattern (alternation of all brands)
        brand_pattern = "|".join(
            re.escape(b) for b in sorted(BRANDS, key=len, reverse=True)
        )
        self.brand_regex = re.compile(rf"\b({brand_pattern})\b", re.IGNORECASE)

        # Compile category patterns
        # First, try to match with prefix (DORMITORIO BOXET, CAMA EUROPEA, etc.)
        self.category_with_prefix_patterns = []
        for prefix in TYPE_PREFIXES:
            for category in BASE_CATEGORIES:
                # Handle special cases where prefix IS the category (CAMA EUROPEA)
                if category.startswith(prefix):
                    continue
                pattern = rf"\b{re.escape(prefix)}\s+{re.escape(category)}\b"
                self.category_with_prefix_patterns.append(
                    (
                        re.compile(pattern, re.IGNORECASE),
                        f"{prefix} {category}",
                        category,
                    )
                )

        # Also match prefix + variant (DORMITORIO EUROPEO -> CAMA EUROPEA)
        category_mappings = {
            "EUROPEO": "CAMA EUROPEA",
            "EUROPEA": "CAMA EUROPEA",
            "AMERICANA": "BOX TARIMA",
            "AMERICANO": "BOX TARIMA",
            "DIVAN": "DIVAN",
            "CON CAJONES": "CAMA CAJONES",  # DORMITORIO CON CAJONES -> CAMA CAJONES
            "CON CAJON": "CAMA CAJONES",  # Handle singular
            "CON CAJÓN": "CAMA CAJONES",  # Handle accent
        }
        for variant, base_cat in category_mappings.items():
            for prefix in TYPE_PREFIXES:
                pattern = rf"\b{re.escape(prefix)}\s+{re.escape(variant)}\b"
                self.category_with_prefix_patterns.append(
                    (
                        re.compile(pattern, re.IGNORECASE),
                        f"{prefix} {variant}",
                        base_cat,
                    )
                )

        # Also handle "CAMA DIVAN" specifically (maps to DIVAN)
        self.category_with_prefix_patterns.append(
            (
                re.compile(r"\bCAMA\s+DIVAN\b", re.IGNORECASE),
                "CAMA DIVAN",
                "DIVAN",
            )
        )

        # Handle "BASE BOX EUROPEO" -> CAMA EUROPEA
        self.category_with_prefix_patterns.insert(
            0,
            (
                re.compile(r"\bBASE\s+(?:\w+\s+)?BOX\s+EUROPEO\b", re.IGNORECASE),
                "BASE BOX EUROPEO",
                "CAMA EUROPEA",
            ),
        )

        # Handle "BASE ... CON CAJONES" or "BASE ... CON X CAJONES" -> BASE CAJONES
        # This pattern allows brand names and sizes between BASE and CON CAJONES
        # Use .+? to match any characters (including 1.5 PLAZAS)
        self.category_with_prefix_patterns.insert(
            0,
            (
                re.compile(
                    r"\bBASE\s+.+?\bCON\s+(?:\d+\s+)?CAJ[OÓ]N(?:ES)?\b", re.IGNORECASE
                ),
                "BASE CAJONES",
                "BASE CAJONES",
            ),
        )

        # Handle "KIT BASE CON CAJONES" -> BASE CAJONES
        self.category_with_prefix_patterns.insert(
            0,
            (
                re.compile(r"\bKIT\s+BASE\s+CON\s+CAJ[OÓ]N(?:ES)?\b", re.IGNORECASE),
                "KIT BASE CAJONES",
                "BASE CAJONES",
            ),
        )

        # Handle "DORMITORIO AMERICANO CON CAJONES" -> CAMA CAJONES
        self.category_with_prefix_patterns.insert(
            0,
            (
                re.compile(
                    r"\bDORMITORIO\s+(?:AMERICANO|EUROPEO)?\s*CON\s+CAJ[OÓ]N(?:ES)?\b",
                    re.IGNORECASE,
                ),
                "DORMITORIO CON CAJONES",
                "CAMA CAJONES",
            ),
        )

        # Handle "DORMITORIO CON CAJÓN" (singular with accent)
        self.category_with_prefix_patterns.insert(
            0,
            (
                re.compile(
                    r"\bDORMITORIO\s+CON\s+CAJ[OÓ]N\b",
                    re.IGNORECASE,
                ),
                "DORMITORIO CON CAJONES",
                "CAMA CAJONES",
            ),
        )

        # Handle "KIT DORMITORIO ... CON CAJONES"
        self.category_with_prefix_patterns.insert(
            0,
            (
                re.compile(
                    r"\bKIT\s+DORMITORIO\s+.*?\bCON\s+CAJ[OÓ]N(?:ES)?\b",
                    re.IGNORECASE,
                ),
                "KIT DORMITORIO CAJONES",
                "CAMA CAJONES",
            ),
        )

        # Compile base category patterns (for direct matches)
        # Create patterns that match both accented and unaccented versions
        self.category_patterns = []
        for cat in sorted(BASE_CATEGORIES, key=len, reverse=True):
            # Create pattern that handles common accent variations
            pattern_str = cat
            pattern_str = pattern_str.replace("O", "[OÓ]")
            pattern_str = pattern_str.replace("A", "[AÁ]")
            pattern_str = pattern_str.replace("E", "[EÉ]")
            pattern_str = pattern_str.replace("I", "[IÍ]")
            pattern_str = pattern_str.replace("U", "[UÚ]")
            pattern_str = rf"\b{pattern_str}\b"
            self.category_patterns.append((re.compile(pattern_str, re.IGNORECASE), cat))

        # Compile accessory pattern for splitting
        self.accessory_split_regex = re.compile(r"\s*\+\s*|\s+CON\s+", re.IGNORECASE)

        # Compile accessory extraction patterns
        self.accessory_patterns = [
            re.compile(pattern, re.IGNORECASE) for pattern in ACCESSORY_PATTERNS
        ]

    def extract_attributes_batch(
        self, products: List[Dict], batch_size: int = 25, delay: float = 0
    ) -> List[Dict]:
        """
        Extract attributes from products

        Args:
            products: List of product dictionaries with 'title' field
            batch_size: Ignored (kept for API compatibility)
            delay: Ignored (kept for API compatibility)

        Returns:
            List of products with extracted attributes added
        """
        results = []

        # Create progress bar if verbose
        pbar = tqdm(
            products,
            desc="Extracting attributes (regex)",
            disable=not self.verbose,
            unit="products",
        )

        for product in pbar:
            attrs = self._extract_single(product)
            product_with_attrs = product.copy()
            product_with_attrs.update(attrs)
            results.append(product_with_attrs)

        if self.verbose:
            logger.info(f"Extraction complete: {len(results)} products processed")
            logger.info(
                f"Success: {self.successful_extractions}, "
                f"Partial: {self.partial_extractions}, "
                f"Failed: {self.failed_extractions}"
            )

        return results

    def _extract_single(self, product: Dict) -> Dict:
        """Extract attributes from a single product"""
        title = product.get("title", "")
        existing_brand = product.get("brand", "")

        self.total_processed += 1

        # Normalize title
        normalized_title = self._normalize_text(title)

        # Split off accessories first
        main_part, accessories = self._split_accessories(normalized_title)

        # Extract brand
        brand = self._extract_brand(main_part, existing_brand)

        # Extract product type and base category
        product_type, base_category = self._extract_category(main_part)

        # Extract size
        size, main_part_no_size = self._extract_size(main_part)

        # Extract base model (what's left after removing known parts)
        base_model = self._extract_model(
            main_part_no_size, brand, product_type, base_category
        )

        # Extract color (remaining meaningful word after model)
        color = self._extract_color(main_part_no_size, brand, base_model, size)

        # For KIT products, brand/model/size might be in the last accessory
        # Check accessories if we're missing key info
        if accessories and (not brand or not base_model or not size):
            # Combine all accessories into one string to search
            accessories_combined = " ".join(accessories)

            # Try to extract missing brand from accessories
            if not brand:
                brand = self._extract_brand(accessories_combined, existing_brand)

            # Try to extract missing size from accessories
            if not size:
                size, _ = self._extract_size(accessories_combined)

            # Try to extract missing model from accessories
            if not base_model or base_model == "UNKNOWN":
                base_model = self._extract_model(
                    accessories_combined, brand, product_type, base_category
                )

        # Calculate confidence
        confidence = self._calculate_confidence(
            brand, product_type, base_category, base_model, size
        )

        # Update stats
        if confidence >= 0.9:
            self.successful_extractions += 1
        elif confidence >= 0.5:
            self.partial_extractions += 1
        else:
            self.failed_extractions += 1

        return {
            "original_title": title,
            "brand": brand or "UNKNOWN",
            "product_type": product_type or "UNKNOWN",
            "base_category": base_category or "UNKNOWN",
            "base_model": base_model or "UNKNOWN",
            "variant_attributes": {
                "size": size,
                "color": color,
                "accessories": accessories,
                "features": [],
            },
            "confidence": confidence,
        }

    def _normalize_text(self, text: str) -> str:
        """Normalize text for consistent matching"""
        # Convert to uppercase
        text = text.upper()

        # Normalize unicode (handle accents)
        # Keep accented chars but normalize combining characters
        text = unicodedata.normalize("NFC", text)

        # Remove special chars but keep accents, spaces, hyphens, plus signs, dots and commas (for sizes like 1.5)
        text = re.sub(r"[^\w\s\+\-\.,ÁÉÍÓÚÑÜ]", " ", text)

        # Normalize multiple spaces
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _remove_accents(self, text: str) -> str:
        """Remove accents for comparison"""
        nfkd = unicodedata.normalize("NFKD", text)
        return "".join(c for c in nfkd if not unicodedata.combining(c))

    def _split_accessories(self, title: str) -> Tuple[str, List[str]]:
        """Split title into main part and accessories"""
        # First, protect "CON CAJONES" and "CON CAJÓN" from being split - it's part of product type
        protected_title = re.sub(
            r"\bCON\s+(?:\d+\s+)?CAJ[OÓ]N(?:ES)?\b",
            "CONCAJONES_PLACEHOLDER",
            title,
            flags=re.IGNORECASE,
        )

        parts = self.accessory_split_regex.split(protected_title)

        if len(parts) <= 1:
            # Restore placeholder
            return title.replace("CONCAJONES_PLACEHOLDER", "CON CAJONES"), []

        main_part = parts[0].strip()
        # Restore placeholder in main part
        main_part = main_part.replace("CONCAJONES_PLACEHOLDER", "CON CAJONES")

        accessory_parts = [p.strip() for p in parts[1:] if p.strip()]

        # Clean up accessory descriptions
        accessories = []
        for acc in accessory_parts:
            # Restore placeholder if present
            acc = acc.replace("CONCAJONES_PLACEHOLDER", "CON CAJONES")
            acc_clean = acc.strip()
            if acc_clean:
                accessories.append(acc_clean)

        return main_part, accessories

    def _extract_brand(self, text: str, existing_brand: str) -> Optional[str]:
        """Extract brand from text"""
        # First, try to find brand in text
        match = self.brand_regex.search(text)
        if match:
            brand = match.group(1).upper()
            # Normalize brand names
            brand = self._remove_accents(brand)
            if brand == "PARAISO":
                return "PARAISO"
            if brand == "CISNE":
                return "EL CISNE"
            if brand == "FORLI":
                return "FORLI"
            return brand

        # Fall back to existing brand from product data
        if existing_brand:
            return self._remove_accents(existing_brand.upper())

        return None

    def _extract_category(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract product type and base category

        Returns:
            Tuple of (product_type, base_category)
            e.g., ("DORMITORIO BOXET", "BOXET") or ("CAMA EUROPEA", "CAMA EUROPEA")
        """
        # First, try prefixed categories (DORMITORIO BOXET, DORMITORIO EUROPEO, etc.)
        for pattern, product_type, base_category in self.category_with_prefix_patterns:
            if pattern.search(text):
                return product_type, base_category

        # Then try direct category matches
        for pattern, category in self.category_patterns:
            if pattern.search(text):
                # Check if there's a prefix before it
                prefix_match = None
                for prefix in TYPE_PREFIXES:
                    prefix_pattern = re.compile(
                        rf"\b{re.escape(prefix)}\s+", re.IGNORECASE
                    )
                    if prefix_pattern.search(text):
                        prefix_match = prefix
                        break

                if prefix_match and not category.startswith(prefix_match):
                    return f"{prefix_match} {category}", category
                return category, category

        # Check for standalone prefixes that imply a category
        # e.g., "DORMITORIO ROSEN..." without explicit category
        text_normalized = self._remove_accents(text)
        if "DORMITORIO" in text_normalized:
            # Try to infer from context
            if "EUROPEO" in text_normalized or "EUROPEA" in text_normalized:
                return "DORMITORIO EUROPEO", "CAMA EUROPEA"
            if "AMERICANO" in text_normalized or "AMERICANA" in text_normalized:
                return "DORMITORIO AMERICANO", "BOX TARIMA"
            # Default dormitorio without qualifier - could be various types
            return "DORMITORIO", None

        if "CAMA" in text_normalized:
            # Check for "CAMA CON CAJONES"
            if "CAJONES" in text_normalized or "CAJON" in text_normalized:
                return "CAMA CAJONES", "CAMA CAJONES"
            # Check for "CAMA DIVAN"
            if "DIVAN" in text_normalized:
                return "CAMA DIVAN", "DIVAN"
            # Generic CAMA (without qualifier) - likely a bed
            # This catches "CAMA SERTA CANTABRIA..." type products
            return "CAMA", "CAMA"

        # Handle CONJUNTO (bundles)
        if "CONJUNTO" in text_normalized:
            return "CONJUNTO", "CONJUNTO"

        return None, None

    def _extract_size(self, text: str) -> Tuple[Optional[str], str]:
        """
        Extract size from text

        Returns:
            Tuple of (normalized_size, text_with_size_removed)
        """
        for pattern, normalized in self.size_patterns:
            match = pattern.search(text)
            if match:
                # Remove the matched size from text
                text_without = pattern.sub("", text).strip()
                text_without = re.sub(r"\s+", " ", text_without)
                return normalized, text_without

        return None, text

    def _extract_model(
        self,
        text: str,
        brand: Optional[str],
        product_type: Optional[str],
        base_category: Optional[str],
    ) -> Optional[str]:
        """Extract the base model name"""
        # Remove known parts from text
        remaining = text

        # Remove brand
        if brand:
            brand_pattern = re.compile(rf"\b{re.escape(brand)}\b", re.IGNORECASE)
            remaining = brand_pattern.sub("", remaining)
            # Also try without accents
            brand_no_accent = self._remove_accents(brand)
            if brand_no_accent != brand:
                brand_pattern = re.compile(
                    rf"\b{re.escape(brand_no_accent)}\b", re.IGNORECASE
                )
                remaining = brand_pattern.sub("", remaining)

        # Remove product type words
        if product_type:
            for word in product_type.split():
                word_pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
                remaining = word_pattern.sub("", remaining)
                # Also try with/without accents
                word_no_accent = self._remove_accents(word)
                if word_no_accent != word:
                    word_pattern = re.compile(
                        rf"\b{re.escape(word_no_accent)}\b", re.IGNORECASE
                    )
                    remaining = word_pattern.sub("", remaining)

        # Remove base category words (if different from product_type)
        if base_category and base_category != product_type:
            for word in base_category.split():
                word_pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
                remaining = word_pattern.sub("", remaining)
                # Also try with/without accents
                word_no_accent = self._remove_accents(word)
                if word_no_accent != word:
                    word_pattern = re.compile(
                        rf"\b{re.escape(word_no_accent)}\b", re.IGNORECASE
                    )
                    remaining = word_pattern.sub("", remaining)

        # Remove stop words and check for brand names
        words = remaining.split()
        meaningful_words = []

        # Create a set of brand variations for checking
        brand_variations = set()
        for b in BRANDS:
            brand_variations.add(b.upper())
            brand_variations.add(self._remove_accents(b.upper()))

        for word in words:
            word_upper = word.upper()
            word_no_accent = self._remove_accents(word_upper)
            # Skip if it's a stop word
            if word_upper in STOP_WORDS or word_no_accent in STOP_WORDS:
                continue
            # Skip if too short or just digits
            if len(word) <= 1 or word.isdigit():
                continue
            # Skip if it's a brand name (shouldn't be the model)
            if word_upper in brand_variations or word_no_accent in brand_variations:
                continue
            meaningful_words.append(word)

        # The model is typically 1-3 words after brand
        # Common patterns: "TEMPO", "ROYAL CROWN", "PURE FRESH", "POCKET STAR"
        if not meaningful_words:
            return None

        # Take up to 3 words as model name (or until we hit something that looks like a color)
        # Don't include colors in the model name
        model_words = []
        for word in meaningful_words[:4]:  # Max 4 words to consider
            # Skip colors - they're not part of the model name
            if self._is_likely_color(word):
                # If we haven't found any model words yet, skip this color
                # If we have model words, stop here
                if len(model_words) >= 1:
                    break
                continue  # Skip color word
            model_words.append(word)
            # Most models are 1-2 words, sometimes 3
            if len(model_words) >= 3:
                break

        if model_words:
            return " ".join(model_words)

        return None

    def _is_likely_color(self, word: str) -> bool:
        """Check if a word is likely a color"""
        common_colors = {
            "GRIS",
            "AZUL",
            "ROJO",
            "VERDE",
            "NEGRO",
            "BLANCO",
            "MARRON",
            "BEIGE",
            "CHOCOLATE",
            "CHAMPAGNE",
            "GRAFITO",
            "NIEBLA",
            "PLATA",
            "DORADO",
            "CREMA",
            "CAFE",
            "PLOMO",
            "HUMO",
            "ARENA",
            "TERRACOTA",
            "HANOVER",
            "ISSEY",  # Fabric/color names used by brands
        }
        word_upper = self._remove_accents(word.upper())
        return word_upper in common_colors

    def _extract_color(
        self,
        text: str,
        brand: Optional[str],
        base_model: Optional[str],
        size: Optional[str],
    ) -> Optional[str]:
        """Extract color from the remaining text"""
        # Remove known parts
        remaining = text

        # Create set of brand variations to filter out
        brand_variations = set()
        if brand:
            brand_variations.add(brand.upper())
            brand_variations.add(self._remove_accents(brand.upper()))
        # Also add all known brands
        for b in BRANDS:
            brand_variations.add(b.upper())
            brand_variations.add(self._remove_accents(b.upper()))

        if brand:
            brand_pattern = re.compile(rf"\b{re.escape(brand)}\b", re.IGNORECASE)
            remaining = brand_pattern.sub("", remaining)
            brand_no_accent = self._remove_accents(brand)
            if brand_no_accent != brand:
                remaining = re.sub(
                    rf"\b{re.escape(brand_no_accent)}\b",
                    "",
                    remaining,
                    flags=re.IGNORECASE,
                )

        if base_model:
            for word in base_model.split():
                remaining = re.sub(
                    rf"\b{re.escape(word)}\b", "", remaining, flags=re.IGNORECASE
                )

        # Remove category-related words (both with and without accents)
        for stop in STOP_WORDS:
            remaining = re.sub(
                rf"\b{re.escape(stop)}\b", "", remaining, flags=re.IGNORECASE
            )

        # Filter words: remove stop words (with accent check) and brand names
        remaining_words = remaining.split()
        filtered_words = []
        for word in remaining_words:
            word_upper = word.upper()
            word_no_accent = self._remove_accents(word_upper)
            # Skip if it's a stop word
            if word_no_accent in STOP_WORDS or word_upper in STOP_WORDS:
                continue
            # Skip if it's a brand name
            if word_upper in brand_variations or word_no_accent in brand_variations:
                continue
            # Skip if too short
            if len(word) <= 1:
                continue
            filtered_words.append(word)
        remaining = " ".join(filtered_words)

        # Clean up
        remaining = re.sub(r"\s+", " ", remaining).strip()

        # What's left might be color(s)
        words = remaining.split()
        color_words = []

        for word in words:
            if len(word) > 1 and not word.isdigit():
                # Check if it's a likely color or could be a color
                color_words.append(word)

        if color_words:
            # Return up to 2 color words (e.g., "GRIS PLATA", "ISSEY GRAFITO")
            return " ".join(color_words[:2])

        return None

    def _calculate_confidence(
        self,
        brand: Optional[str],
        product_type: Optional[str],
        base_category: Optional[str],
        base_model: Optional[str],
        size: Optional[str],
    ) -> float:
        """Calculate confidence score based on extracted fields"""
        score = 0.0

        # Brand is worth 0.25
        if brand and brand != "UNKNOWN":
            score += 0.25

        # Category is worth 0.25
        if base_category and base_category != "UNKNOWN":
            score += 0.25
        elif product_type and product_type != "UNKNOWN":
            score += 0.15

        # Model is worth 0.3
        if base_model and base_model != "UNKNOWN":
            score += 0.3

        # Size is worth 0.2
        if size:
            score += 0.2

        return round(min(score, 1.0), 2)

    def get_stats(self) -> Dict:
        """Get extraction statistics"""
        return {
            "total_processed": self.total_processed,
            "successful_extractions": self.successful_extractions,
            "partial_extractions": self.partial_extractions,
            "failed_extractions": self.failed_extractions,
            "success_rate": (
                round(self.successful_extractions / self.total_processed * 100, 1)
                if self.total_processed > 0
                else 0
            ),
        }

    def estimate_cost(self, num_products: int, batch_size: int = 25) -> Dict:
        """
        Estimate processing cost (always 0 for regex)

        Args:
            num_products: Number of products to process
            batch_size: Ignored

        Returns:
            Dictionary with cost estimation (all zeros)
        """
        return {
            "num_products": num_products,
            "num_batches": 1,
            "estimated_input_tokens": 0,
            "estimated_output_tokens": 0,
            "estimated_total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "estimated_time_seconds": num_products * 0.001,  # ~1ms per product
            "estimated_time_minutes": round(num_products * 0.001 / 60, 2),
        }
