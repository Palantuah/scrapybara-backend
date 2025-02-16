import os
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(os.environ.get("SUPABASE_URL"),
                         os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def import_raw_articles(csv_path: str):
    """
    Import articles from CSV into Supabase raw_articles table
    
    Maps CSV columns to table fields:
    - Category -> topic
    - Subject -> article_name
    - Body -> content
    - From, Date, Message-ID -> metadata
    """
    try:
        # Read CSV file and replace NaN with None
        df = pd.read_csv(csv_path)
        df = df.where(pd.notna(df), None)

        # Validate required columns
        required_columns = [
            'Subject', 'Body', 'Category', 'From', 'Date', 'Message-ID'
        ]
        if not all(col in df.columns for col in required_columns):
            raise ValueError(f"CSV must contain columns: {required_columns}")

        # Convert DataFrame to list of dictionaries
        articles = []
        for _, row in df.iterrows():
            # Skip rows where required fields are None
            if any(row[col] is None
                   for col in ['Category', 'Subject', 'Body']):
                continue

            article = {
                'topic': row['Category'],
                'article_name': row['Subject'],
                'content': row['Body'],
                'metadata': {
                    'from': row['From'],
                    'date': row['Date'],
                    'message_id': row['Message-ID']
                }
            }
            articles.append(article)

        if not articles:
            print("No valid articles found in CSV")
            return

        # Insert into Supabase
        result = supabase.table('raw_articles').upsert(
            articles, on_conflict='topic,article_name').execute()

        print(f"Successfully imported {len(articles)} articles")
        return result

    except Exception as e:
        print(f"Error importing articles: {str(e)}")
        raise


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python import_raw_articles.py <path_to_csv>")
        sys.exit(1)

    csv_path = sys.argv[1]
    import_raw_articles(csv_path)
