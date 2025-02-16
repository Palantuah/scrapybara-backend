import os
import json
from supabase import create_client
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(os.environ.get("SUPABASE_URL"),
                         os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def import_topic_analyses(json_dir: str):
    """
    Import topic analyses from JSON files into Supabase topic_analyses table
    
    JSON structure:
    {
        "category": str,
        "entries": [{content, timestamp}],
        "analysis": str,
        "keywords": str[],
        "lastUpdated": str
    }
    """
    try:
        analyses = []
        json_files = Path(json_dir).glob('*.json')

        # Print available categories in raw_articles
        result = supabase.table('raw_articles').select('topic').execute()
        available_topics = set(row['topic'] for row in result.data)
        print(f"Available topics in raw_articles: {available_topics}")

        for json_path in json_files:
            print(f"\nProcessing {json_path}")
            with open(json_path) as f:
                data = json.load(f)
                category = data['category']
                print(f"Category from JSON: {category}")

                # First, get source article IDs for this category
                result = supabase.table('raw_articles').select('id').eq(
                    'topic', category).execute()

                source_ids = [row['id'] for row in result.data]

                if not source_ids:
                    print(f"Warning: No source articles found for {category}")
                    continue

                analysis = {
                    'topic': data['category'],
                    'analysis': data['analysis'],
                    'keywords': data['keywords'],
                    'source_article_ids': source_ids,
                    'scrapybara_data': {
                        'urls': [
                            'https://example.com/sports/news1',
                            'https://example.com/sports/news2',
                            'https://example.com/sports/news3'
                        ]
                    }
                }
                analyses.append(analysis)

        if not analyses:
            print("No valid analyses found in JSON files")
            return

        # Insert into Supabase
        result = supabase.table('topic_analyses').insert(analyses).execute()

        print(f"Successfully imported {len(analyses)} topic analyses")
        return result

    except Exception as e:
        print(f"Error importing analyses: {str(e)}")
        raise


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print(
            "Usage: python import_topic_analyses.py <path_to_json_directory>")
        sys.exit(1)

    json_dir = sys.argv[1]
    import_topic_analyses(json_dir)
