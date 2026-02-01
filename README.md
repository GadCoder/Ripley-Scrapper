# Ripley Scraper

A Python scraper for extracting product information from Ripley Peru (simple.ripley.com.pe) with AI-powered product grouping.

## Features

- **API-based scraping**: Direct access to Ripley's internal API - fast, reliable, and captures ALL 3 prices
- **CLI tool**: Easy-to-use command-line interface with comprehensive options
- **AI Product Grouping**: Group products hierarchically using Google Gemini (Brand → Type → Model → Variants)
- **Resume functionality**: Checkpoint system to resume interrupted scraping sessions
- **Automatic retry**: Exponential backoff retry logic for failed requests
- **Batch processing**: Scrape multiple categories at once with combined output

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

Group scraped products hierarchically using Google Gemini AI:

```bash
# Basic usage
python group_products_cli.py products.json

# Custom output file
python group_products_cli.py products.json --output grouped.json

# Dry run (estimate cost only)
python group_products_cli.py products.json --dry-run
```

### Grouping Options

| Option | Description |
|--------|-------------|
| `--output, -o` | Output JSON file (default: input_grouped.json) |
| `--batch-size` | Products per API call (default: 25) |
| `--confidence-threshold` | Minimum confidence for grouping (default: 0.7) |
| `--dry-run` | Estimate cost without making API calls |
| `--api-key` | Gemini API key (overrides .env file) |
| `--quiet, -q` | Minimal output |

### Setup

1. Get a free Gemini API key at https://makersuite.google.com/app/apikey
2. Create a `.env` file:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

## Output Format

### Scraped Products

```json
{
  "id": 1,
  "sku": "2064330571423P",
  "title": "DORMITORIO AMERICANO RIZZOLI NAPOLES QUEEN...",
  "brand": "RIZZOLI",
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
      "brand_name": "RIZZOLI",
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
    "total_models": 45
  }
}
```

## Project Structure

```
├── api_scraper.py          # Core API scraper
├── ripley_cli.py           # Scraper CLI tool
├── group_products_cli.py   # Grouper CLI tool
├── product_grouper/        # AI grouping module
│   ├── __init__.py
│   ├── grouper.py          # Main orchestrator
│   ├── gemini_client.py    # Gemini API client
│   ├── hierarchy_builder.py # Hierarchy construction
│   ├── analytics.py        # Statistics and reports
│   └── validator.py        # Grouping validation
├── tests/                  # Test suite
├── pyproject.toml          # Project configuration
└── requirements.txt        # Dependencies
```

## License

MIT License
