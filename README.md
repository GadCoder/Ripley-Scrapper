# Ripley Scraper

A Python scraper for extracting product information from Ripley Peru (simple.ripley.com.pe) with regex-based product grouping.

## Features

- **API-based scraping**: Direct access to Ripley's internal API - fast, reliable, and captures ALL 3 prices
- **CLI tool**: Easy-to-use command-line interface with comprehensive options
- **Product Grouping**: Group products hierarchically using regex extraction (Brand → Type → Model → Variants)
- **Resume functionality**: Checkpoint system to resume interrupted scraping sessions
- **Automatic retry**: Exponential backoff retry logic for failed requests
- **Batch processing**: Scrape multiple categories at once with combined output
- **Offline capable**: No API keys required - works completely offline

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd Ripley-Scrapper

# Install dependencies using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

## Usage

### CLI Scraper

```bash
# Basic usage - scrape first 3 pages (Ripley products only)
python ripley_cli.py dormitorio

# Scrape all pages in a category
python ripley_cli.py dormitorio --max-pages all

# Include marketplace products (default is Ripley-only)
python ripley_cli.py tecnologia --max-pages 10 --include-marketplace

# Scrape multiple categories at once
python ripley_cli.py dormitorio tecnologia electrohogar --max-pages 5

# Combine multiple categories into one file
python ripley_cli.py dormitorio tecnologia --max-pages 10 --combine --output combined.json

# Enable checkpoint saving (auto-save every 10 pages)
python ripley_cli.py dormitorio --max-pages 50 --save-checkpoint

# Resume from checkpoint
python ripley_cli.py --resume checkpoint_dormitorio_20260115_120000.json
```

### CLI Options

| Option | Description |
|--------|-------------|
| `categories` | One or more category slugs (dormitorio, tecnologia, etc.) |
| `--max-pages N` | Limit pages to scrape (default: 3, use `all` for everything) |
| `--output FILE` | Custom output filename |
| `--delay SECONDS` | Delay between requests (default: 0.5) |
| `--include-marketplace` | Include marketplace sellers (default: Ripley only) |
| `--save-checkpoint` | Enable automatic checkpoint saving |
| `--resume FILE` | Resume from checkpoint file |
| `--combine` | Combine multiple categories into one file |
| `--quiet` | Suppress progress output |

### Python API

```python
from api_scraper import RipleyAPIScraper

scraper = RipleyAPIScraper()

# Scrape a category (all pages by default)
products = scraper.scrape_category("dormitorio", max_pages=5)

# Save results
scraper.save_to_json("products.json")
scraper.print_summary()
```

## Product Grouping

Group scraped products hierarchically using regex-based extraction:

```bash
# Basic usage
python group_products_cli.py products.json

# Custom output file
python group_products_cli.py products.json --output grouped.json

# Verbose mode
python group_products_cli.py products.json --verbose
```

### Grouping Features

- **Fast**: Processes 4,000+ products in ~1.4 seconds
- **Free**: No API costs - uses deterministic regex patterns
- **Offline**: Works without internet connection
- **Accurate**: ~99.4% grouping success rate

### Grouping Options

| Option | Description |
|--------|-------------|
| `--output, -o` | Output JSON file (default: input_grouped.json) |
| `--confidence-threshold` | Minimum confidence for grouping (default: 0.7) |
| `--quiet, -q` | Minimal output |

## Output Format

### Scraped Products

```json
{
  "id": 1,
  "sku": "2064330571423P",
  "title": "DORMITORIO AMERICANO RIZZOLI NAPOLES QUEEN...",
  "brand": "ROSEN",
  "normal_price": 4399,
  "internet_price": 2099,
  "ripley_price": 1979,
  "currency": "PEN",
  "discount_percentage": 55,
  "is_marketplace": false,
  "in_stock": true
}
```

### Grouped Products

```json
{
  "brands": [
    {
      "brand_name": "ROSEN",
      "product_types": [
        {
          "type_name": "DORMITORIO AMERICANO",
          "models": [
            {
              "base_model": "NAPOLES",
              "available_sizes": ["QUEEN", "KING"],
              "variants": [...]
            }
          ]
        }
      ]
    }
  ],
  "metadata": {
    "total_products": 100,
    "total_brands": 15,
    "total_models": 45,
    "processing_time_seconds": 1.4
  }
}
```

## Supported Product Categories

The regex extractor supports the following product types:

**Beds & Mattresses:**
- COLCHON, CAMA EUROPEA, BOX TARIMA, BOX SPRING, DIVAN, BOXET
- BED BOXET, CAMA CAJONES, BASE EUROPEA, BASE BOX TARIMA, etc.

**Furniture:**
- BERGERE, RESPALDO, VELADOR, MESA, POLTRONA, BUTACA, SOFA
- CABECERA, ALMOHADA

**Sizes:**
- 1PLZ, 1.5PLZ, 2PLZ, QUEEN, KING, 1C, 2C, 3C

**Brands:**
- ROSEN, PARAISO, DRIMER, SIMMONS, SERTA, DROM, MICA
- FORLI, RIZZOLI, EL CISNE, RIPLEY HOME, MAISON LINETT

## Project Structure

```
├── api_scraper.py          # Core API scraper
├── ripley_cli.py           # Scraper CLI tool
├── group_products_cli.py   # Grouper CLI tool
├── product_grouper/        # Product grouping module
│   ├── __init__.py
│   ├── grouper.py          # Main orchestrator
│   ├── regex_extractor.py  # Regex-based attribute extraction
│   ├── hierarchy_builder.py # Hierarchy construction
│   ├── analytics.py        # Statistics and reports
│   └── validator.py        # Grouping validation
├── tests/                  # Test suite
├── pyproject.toml          # Project configuration
└── requirements.txt        # Dependencies
```

## License

MIT License
