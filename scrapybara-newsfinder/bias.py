from scrapybara import Scrapybara
from scrapybara.anthropic import Anthropic
from scrapybara.tools import BrowserTool
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv
import os
#from scrapybara.prompts import UBUNTU_SYSTEM_PROMPT


"""
# # AP News
    browser({{"command": "new_context"}})
    browser({{"command": "go_to", "url": "{SEARCH_URLS["AP News"]["url"].format(topic)}"}})
    browser({{"command": "wait", "seconds": 2}})
    browser({{"command": "click", "selector": "{SEARCH_URLS["AP News"]["selector"]}"}})
    browser({{"command": "wait", "seconds": 2}})
    url = browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
    print("AP News URL:", url if url else "not_found")
    urls.append(ArticleURL(url=url if url else "not_found", source="AP News"))

    
    # The Guardian
    browser({{"command": "new_context"}})
    browser({{"command": "go_to", "url": "{SEARCH_URLS["The Guardian"]["url"].format(topic)}"}})
    
    browser({{"command": "click", "selector": "{SEARCH_URLS["The Guardian"]["selector"]}"}})
    
    url = browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
    print("Guardian URL:", url if url else "not_found")
    urls.append(ArticleURL(url=url if url else "not_found", source="The Guardian"))

     # BBC
    browser({{"command": "new_context"}})
    browser({{"command": "go_to", "url": "{SEARCH_URLS["BBC"]["url"].format(topic)}"}})
    
    browser({{"command": "click", "selector": "{SEARCH_URLS["BBC"]["selector"]}"}})
    
    url = browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
    print("BBC URL:", url if url else "not_found")
    urls.append(ArticleURL(url=url if url else "not_found", source="BBC"))

    # Fox News
    browser({{"command": "new_context"}})
    browser({{"command": "go_to", "url": "{SEARCH_URLS["Fox News"]["url"].format(topic)}"}})
    
    browser({{"command": "click", "selector": "{SEARCH_URLS["Fox News"]["selector"]}"}})
    
    url = browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
    print("Fox News URL:", url if url else "not_found")
    urls.append(ArticleURL(url=url if url else "not_found", source="Fox News"))

    # The Hill
    browser({{"command": "new_context"}})
    browser({{"command": "go_to", "url": "{SEARCH_URLS["The Hill"]["url"].format(topic)}"}})
    
    browser({{"command": "click", "selector": "{SEARCH_URLS["The Hill"]["selector"]}"}})
    
    url = browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
    print("The Hill URL:", url if url else "not_found")
    urls.append(ArticleURL(url=url if url else "not_found", source="The Hill"))

"""
load_dotenv()

class ArticleURL(BaseModel):
    url: str
    source: str

class URLCollection(BaseModel):
    urls: List[ArticleURL]

# List of news sources to check (can be moved to a config file later)
NEWS_SOURCES = [
    "www.apnews.com",
    "theguardian.com",
    "www.foxnews.com",
    "www.propublica.org"
]

# Add after imports
SEARCH_URLS = {
    "AP News": {
        "url": "https://apnews.com/search?q={}",
        "selector": "div.PagePromo-content a"
    },
    "The Guardian": {
        "url": "https://www.google.co.uk/search?q={}&as_sitesearch=www.theguardian.com",
        "selector": "div.g > div > div > div > a"
    },
    "Fox News": {
        "url": "https://www.foxnews.com/search-results/search#q={}",
        "selector": "ssearch-results article a"
    }
}

def collect_urls(client: Scrapybara, instance, topic: str) -> List[ArticleURL]:
    """
    Collect article URLs from multiple sources.
    """
    prompt = f"""
    ```python
    urls = []
    # AP News
    browser({{"command": "new_context"}})
    browser({{"command": "go_to", "url": "{SEARCH_URLS["AP News"]["url"].format(topic)}"}})
    browser({{"command": "wait", "seconds": 2}})
    browser({{"command": "click", "selector": "{SEARCH_URLS["AP News"]["selector"]}"}})
    browser({{"command": "wait", "seconds": 2}})
    url = browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
    print("AP News URL:", url if url else "not_found")
    urls.append(ArticleURL(url=url if url else "not_found", source="AP News"))

    
    # The Guardian
    browser({{"command": "new_context"}})
    browser({{"command": "go_to", "url": "{SEARCH_URLS["The Guardian"]["url"].format(topic)}"}})
    
    browser({{"command": "click", "selector": "{SEARCH_URLS["The Guardian"]["selector"]}"}})
    
    url = browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
    print("Guardian URL:", url if url else "not_found")
    urls.append(ArticleURL(url=url if url else "not_found", source="The Guardian"))

    
    # Fox News
    browser({{"command": "new_context"}})
    browser({{"command": "go_to", "url": "{SEARCH_URLS["Fox News"]["url"].format(topic)}"}})
    
    browser({{"command": "click", "selector": "{SEARCH_URLS["Fox News"]["selector"]}"}})
    
    url = browser({{"command": "evaluate", "code": "document.querySelector('link[rel=\"canonical\"]').getAttribute('href')"}})
    print("Fox News URL:", url if url else "not_found")
    urls.append(ArticleURL(url=url if url else "not_found", source="Fox News"))

    return URLCollection(urls=urls)
    ```
    """

    model = Anthropic()

    response = client.act(
        model=model,
        tools=[BrowserTool(instance)],
        system="Execute the Python code and return the URLCollection.",
        prompt=prompt,
        schema=URLCollection,
        temperature=0.7
    )

    return response.output.urls

def main():
    topic = input("Enter the topic to analyze: ")

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
        urls = collect_urls(client, instance, topic)
        print(f"\nFound {len(urls)} articles:")

        for i, article in enumerate(urls, 1):
            print(f"\nArticle {i}:")
            print(f"Source: {article.source}")
            print(f"URL: {article.url}")

    finally:
        instance.stop()
        print("\nInstance stopped")

if __name__ == "__main__":
    main()
