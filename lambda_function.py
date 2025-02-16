import json
from generatefinal import generate_newsletter

def lambda_handler(event, context):
    try:
        # Extract parameters from the event
        body = json.loads(event.get('body', '{}'))
        
        # Get parameters with defaults
        category_dir = body.get('category_dir', 'outputs/category_reports')
        categories = body.get('categories', ["tech", "sports", "global news", "us news", "finance"])
        openai_key = body.get('openai_key')
        anthropic_key = body.get('anthropic_key')
        
        # Validate required parameters
        if not openai_key or not anthropic_key:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing required API keys'
                })
            }
        
        # Generate the newsletter
        newsletter_text, score = generate_newsletter(
            category_dir=category_dir,
            categories=categories,
            openai_key=openai_key,
            anthropic_key=anthropic_key
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'newsletter': newsletter_text,
                'score': score,
                'categories': categories
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        } 