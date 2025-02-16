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
                Find 3 reliable sources about {keyword} from www.google.com. Avoid sources with bias,
                and prefer sources that are known for their accuracy and reliability. When outputting a 
                source, include the title, url, and reliability notes.
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

