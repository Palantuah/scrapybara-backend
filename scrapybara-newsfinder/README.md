# W25 Scraping Demo

A demonstration of Scrapybara's agent endpoints (act, scrape) to gather and interact with YC W25 company data.

## Features

- Automated scraping of YC W25 companies
- Contact information gathering
- Automated message drafting using LibreOffice
- Schema-based data extraction
- Multi-step automation workflow

## Prerequisites

- Python 3.8+
- Poetry
- Scrapybara API key (get one at [scrapybara.com](https://scrapybara.com))

## Installation

1. Navigate to the demo directory:

```bash
cd w25-scraping
```

2. Install dependencies with Poetry:

```bash
poetry install
```

3. Create a `.env` file in the root directory:

```bash
SCRAPYBARA_API_KEY=your_scrapybara_api_key_here
```

## Usage

Run the project using Poetry:

```bash
poetry run python main.py
```

The script will:

1. Start a Scrapybara instance
2. Scrape W25 companies from YC's website
3. Find contact information for each company
4. Draft messages using LibreOffice
5. Clean up and stop the instance

## How It Works

### Data Scraping

Uses Scrapybara's scrape endpoint with a defined schema:

```python
response = instance.agent.scrape(
    cmd="Go to https://ycombinator.com/companies, set batch filter to W25, and scrape all W25 companies.",
    schema={
        "companies": [
            {
                "name": "str",
                "description": "str",
                "tags": "str[]",
            }
        ]
    },
)
```

### Contact Information Gathering

Automatically searches for the best contact method:

```python
contact_info = instance.agent.scrape(
    cmd=f"Find the best way to contact YC W25 company {company['name']}...",
    schema={
        "contact_method": "str",
        "contact_details": "str",
    },
)
```

### Message Drafting

Uses the act endpoint to interact with LibreOffice:

```python
instance.agent.act(
    cmd=f"Open LibreOffice, draft a two sentence message..."
)
```

## Configuration

### Environment Variables

Required in `.env`:

```bash
SCRAPYBARA_API_KEY=your_scrapybara_api_key
```

### Instance Settings

The script uses a large instance type for better performance:

```python
instance = client.start(instance_type="large")
```

## Support

For support, please [create an issue](https://github.com/Scrapybara/scrapybara-demos/issues) in the repository.
