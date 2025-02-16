import os
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase = create_client(os.environ.get("SUPABASE_URL"),
                         os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))


def cleanup_tables():
    """
    Clean up the raw_articles and topic_analyses tables
    """
    try:
        # Delete all records from topic_analyses
        result = supabase.table('topic_analyses').delete().execute()
        print("Cleaned topic_analyses table")

        # Delete all records from raw_articles
        result = supabase.table('raw_articles').delete().execute()
        print("Cleaned raw_articles table")

    except Exception as e:
        print(f"Error cleaning tables: {str(e)}")
        raise


if __name__ == "__main__":
    cleanup_tables()
