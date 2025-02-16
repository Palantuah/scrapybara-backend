from scrapybara import Scrapybara
from scrapybara.anthropic import Anthropic
from scrapybara.tools import BrowserTool
#from scrapybara.prompts import UBUNTU_SYSTEM_PROMPT
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv
import os
import json
from datetime import datetime
import time

load_dotenv()


"""
AP News:
                1. Go to: {SEARCH_URLS["AP News"].format(keyword)}
                2. Click first article link: browser({{"command": "click", "selector": "div.PagePromo-content a"}})
                3. Get the URL: browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
                4. Get the article title
                5. Go to: www.google.com

The Guardian:

                1. Go to: {SEARCH_URLS["The Guardian"].format(keyword)}
                2. Click first result: browser({{"command": "click", "selector": "div.g > div > div > div > a"}})
                3. Get the URL: browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
                4. Get the article title
BBC:
                1. Go to: {SEARCH_URLS["BBC"].format(keyword)}
                2. Click first result: browser({{"command": "click", "selector": "div.ssrcss-1ynlzyd-PromoSwitchLayoutAtBreakpoints a"}})
                3. Get the URL: browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
                4. Get the article title

                Fox News:
                1. Go to: {SEARCH_URLS["Fox News"]["url"].format(keyword)}
                2. Wait for search results: browser({{"command": "wait", "seconds": 5}})
                3. Click first result: browser({{"command": "click", "selector": "div.search-results article a"}})
                4. Wait for article: browser({{"command": "wait", "seconds": 2}})
                5. Get the URL: browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})

                The Hill:
                1. Go to: {SEARCH_URLS["The Hill"].format(keyword)}
                2. Click first result: browser({{"command": "click", "selector": "article.article-list__article a"}})
                3. Get the URL: browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
                4. Get the article title

"""
class Source(BaseModel):
    title: str
    url: str
    reliability_notes: str

class ResearchResult(BaseModel):
    phrase: str
    sources: List[Source]
    context_summary: str

def save_to_json(results: dict, filename: str = "research_results.json"):
    """Save results as simple keyword:url pairs"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return filename

def load_keywords(filename: str = "keywords.json") -> List[str]:
    with open(filename, 'r') as f:
        data = json.load(f)
    return data.get("keywords", [])

# Add after imports
NEWS_SOURCES = [
    "www.apnews.com",
    "www.cnn.com",
    "theguardian.com",
    "www.propublica.org"
]

# Update the search URLs
SEARCH_URLS = {
    "AP News": "https://apnews.com/search?q={}",
    "The Guardian": "https://www.google.co.uk/search?q={}&as_sitesearch=www.theguardian.com",
    "BBC": "https://www.bbc.com/search?q={}",
    "Fox News": "https://www.foxnews.com/search-results/search#q={}",
    "The Hill": "https://thehill.com/?s={}&submit=Search",
    "The Federalist": "https://thefederalist.com/?s={}"
}

def main():
    # Load keywords from JSON
    keywords = load_keywords()
    
    print("Starting instance...")

    # Initialize simple results dictionary
    results = {}

    client = Scrapybara(
        api_key=os.getenv("SCRAPYBARA_API_KEY"),
        timeout=300,
    )
    
    print("\nStarting instance...")
    instance = client.start_ubuntu()
    
    stream_url = instance.get_stream_url().stream_url
    print(f"Stream URL: {stream_url}")
    
    instance.browser.start()
    print("Browser started successfully")

    try:
        for keyword in keywords:
            try:
                print(f"\nResearching: {keyword}")
                
                prompt = f"""
                Find a recent article about {keyword} from AP News.

                1. Go to: {SEARCH_URLS["AP News"].format(keyword)}
                2. Click first article link: browser({{"command": "click", "selector": "div.PagePromo-content a"}})
                3. Get the URL: browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
                4. Store this URL and remember it
                5. Get the article title

                Return the article URL in ResearchResult format with the search phrase "{keyword}".
                """

                research_response = client.act(
                    model=Anthropic(),
                    tools=[BrowserTool(instance)],
                    system="You are a browser automation assistant. Execute commands exactly as written.",
                    prompt=prompt,
                    schema=ResearchResult,
                    temperature=0.7
                )

                # Store just the URL for this keyword
                results[keyword] = research_response.output.sources[0].url
                print(f"Found URL for {keyword}: {results[keyword]}")

            except Exception as e:
                print(f"\nError processing keyword '{keyword}': {str(e)}")
                results[keyword] = "error"
                time.sleep(10)

    finally:
        instance.stop()
        print("\nInstance stopped")

    # Save simplified results
    json_file = save_to_json(results)
    print(f"\nResults saved to: {json_file}")

if __name__ == "__main__":
    main()

