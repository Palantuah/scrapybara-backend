import os
import json
import logging
import openai
import anthropic
from dotenv import load_dotenv
import re

# Load environment variables from .env.local
load_dotenv('.env.local')

# Configure logging to output JSON-formatted logs
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Configuration for category selection
SELECTED_CATEGORIES = [
    "tech",
    "sports",
    "global news",
    "us news",
    "finance"
]

def load_category_analyses(directory: str, categories: list) -> dict:
    """
    Load selected JSON files from the given directory and extract their 'analysis' content.
    Returns a dictionary mapping category names to analysis text.
    
    Args:
        directory (str): Path to category reports directory
        categories (list): List of category names to include
    """
    analyses = {}
    if not os.path.isdir(directory):
        logger.error(json.dumps({
            "event": "error",
            "message": f"Directory not found: {directory}"
        }))
        return analyses

    # Convert categories to lowercase for case-insensitive matching
    categories_lower = [cat.lower() for cat in categories]
    
    for filename in os.listdir(directory):
        if not filename.lower().endswith(".json"):
            continue
            
        # Check if this category is in our selected list
        category_name = os.path.splitext(filename)[0].lower()
        if category_name not in categories_lower:
            logger.info(json.dumps({
                "event": "category_skipped",
                "category": category_name,
                "message": "Category not in selected list"
            }))
            continue

        filepath = os.path.join(directory, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.error(json.dumps({
                "event": "error",
                "message": f"Failed to load JSON file: {filepath}",
                "error": str(e)
            }))
            continue

        # Use original category name from selected list for consistent casing
        original_category = next(cat for cat in categories if cat.lower() == category_name)
        analysis_text = data.get("analysis")
        
        if analysis_text:
            analyses[original_category] = analysis_text
            logger.info(json.dumps({
                "event": "category_loaded",
                "category": original_category,
                "analysis_length": len(analysis_text)
            }))
        else:
            logger.warning(json.dumps({
                "event": "category_missing_analysis",
                "category": original_category,
                "message": "No analysis section found in JSON."
            }))
    return analyses

def generate_newsletter_draft(analyses: dict) -> str:
    """
    Generate newsletter using only categories that were loaded and their content
    """
    # Get actual categories from the analyses dict
    available_categories = list(analyses.keys())
    
    # Build content sections with clear category separation
    content_sections = []
    for category, analysis in analyses.items():
        section = f"Category: {category}\nContent:\n{analysis}"
        content_sections.append(section)
    combined_content = "\n\n".join(content_sections)
    
    # Build category-specific prompt sections
    category_sections = "\n".join([
        f"- {category}" for category in available_categories
    ])

    system_prompt = f"""You are creating a daily digest newsletter that synthesizes content from exactly these categories:
{category_sections}

KEY RULES:
1. ONLY include content from the provided source materials
2. NEVER generate content not present in sources
3. ONLY cover these specific categories
4. Maintain original details and facts
5. Group content by these exact category names"""

    user_prompt = f"""Create a multi-category newsletter from ONLY the provided content. For each category:

1. Use only information from that category's source content
2. Do not add any information not present in sources
3. Group under these exact category headings:
{category_sections}
4. STRICTLY maintain 400-500 words per section - this is crucial
5. Use a friendly, engaging tone while maintaining factual accuracy

IMPORTANT LENGTH REQUIREMENT:
- Each section MUST be between 400-500 words
- Current categories requiring 400-500 words each: {category_sections}
- Total length should be {len(analyses) * 450} words approximately

Content to synthesize by category:
{combined_content}"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    # Increase max_tokens to ensure we get full-length content
    try:
        logger.info(json.dumps({"event": "draft_generation_start"}))
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=4000  # Increased to accommodate longer sections
        )
    except Exception as e:
        logger.error(json.dumps({
            "event": "error",
            "stage": "draft_generation",
            "message": "OpenAI API call failed",
            "error": str(e)
        }))
        raise

    draft_text = response.choices[0].message.content.strip()
    finish_reason = response.choices[0].finish_reason
    logger.info(json.dumps({
        "event": "draft_generated",
        "finish_reason": finish_reason,
        "tokens_used": response.usage.total_tokens if hasattr(response, "usage") else None
    }))
    
    if finish_reason == "length":
        logger.warning(json.dumps({
            "event": "warning",
            "message": "Draft may be truncated due to max token limit."
        }))
    return draft_text

def evaluate_newsletter(content: str) -> tuple:
    """
    Use Anthropic's Claude to evaluate the newsletter content on various criteria.
    Returns a tuple (score, suggestions) where score is a float or int overall score, and suggestions is a text of improvement suggestions.
    """
    eval_prompt = (
        "You are an AI assistant evaluating a newsletter draft. "
        "Here is the newsletter content:\n\n"
        f"{content}\n\n"
        "You MUST provide:\n"
        "1. A numerical score from 1-10 (you must give a number)\n"
        "2. 2-3 specific suggestions for improving the newsletter\n\n"
        "Your response MUST start with 'Score: ' followed by a number, then 'Suggestions:' on a new line.\n\n"
        "Evaluate based on:\n"
        "- Section lengths (should be 400-500 words each)\n"
        "- Writing quality and engagement\n"
        "- Factual accuracy and detail preservation\n"
        "- Overall structure and flow\n\n"
        "Format exactly like this:\n"
        "Score: [number]\n"
        "Suggestions:\n"
        "- [first suggestion]\n"
        "- [second suggestion]\n"
        "- [third suggestion]"
    )

    try:
        logger.info(json.dumps({"event": "evaluation_start"}))
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model="claude-2",
            max_tokens=1000,
            temperature=0.0,
            messages=[{"role": "user", "content": eval_prompt}]
        )
        
        eval_content = response.content[0].text if response.content else ""
        logger.info(json.dumps({"event": "evaluation_done"}))

        # Extract score - now with stricter parsing
        score_match = re.search(r'Score:\s*(\d+(?:\.\d+)?)', eval_content, re.IGNORECASE)
        if not score_match:
            # If no score found, try again with a more direct prompt
            logger.warning(json.dumps({
                "event": "warning",
                "message": "No score found in evaluation, retrying with direct prompt"
            }))
            response = client.messages.create(
                model="claude-2",
                max_tokens=100,
                temperature=0.0,
                messages=[{
                    "role": "user", 
                    "content": "Based on the newsletter you just evaluated, give ONLY a number from 1-10. Just the number, nothing else:"
                }]
            )
            retry_content = response.content[0].text if response.content else ""
            score_match = re.search(r'(\d+(?:\.\d+)?)', retry_content)

        score = float(score_match.group(1)) if score_match else 5.0  # Default to 5 if still no score
        suggestions = eval_content

        logger.info(json.dumps({
            "event": "evaluation_processed",
            "score": score
        }))

        return score, suggestions

    except Exception as e:
        logger.error(json.dumps({
            "event": "error",
            "stage": "evaluation",
            "message": "Anthropic API call failed",
            "error": str(e)
        }))
        raise

def refine_newsletter(draft: str, feedback: str) -> str:
    """
    Use GPT-4 to refine the newsletter draft based on Claude's feedback.
    Returns the refined newsletter draft text.
    """
    # Get the categories from the current draft
    categories = []
    for line in draft.split('\n'):
        if line.strip() in SELECTED_CATEGORIES:
            categories.append(line.strip())
    
    category_sections = "\n".join([
        f"- {category}" for category in categories
    ])

    system_prompt = f"""You are creating a daily digest newsletter that synthesizes content from exactly these categories:
{category_sections}

KEY RULES:
1. ONLY include content from the provided source materials
2. NEVER generate content not present in sources
3. ONLY cover these specific categories
4. Maintain original details and facts
5. Group content by these exact category names

IMPROVEMENT FEEDBACK TO ADDRESS:
{feedback}"""

    user_prompt = (
        "Here is the current newsletter draft that needs improvement:\n\n"
        f"{draft}\n\n"
        "Please refine this newsletter draft while:\n"
        "1. Maintaining all factual content\n"
        "2. Addressing the improvement feedback\n"
        "3. Keeping each section 400-500 words\n"
        "4. Using the same category structure\n"
        "5. Ensuring a friendly, engaging tone\n\n"
        "Provide the improved newsletter in plain text format."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    try:
        logger.info(json.dumps({"event": "refinement_start"}))
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
    except Exception as e:
        logger.error(json.dumps({
            "event": "error",
            "stage": "refinement",
            "message": "OpenAI API call failed during refinement",
            "error": str(e)
        }))
        raise

    refined_text = response.choices[0].message.content.strip()
    finish_reason = response.choices[0].finish_reason
    logger.info(json.dumps({
        "event": "refinement_done",
        "finish_reason": finish_reason,
        "tokens_used": response.usage.total_tokens if hasattr(response, "usage") else None
    }))
    if finish_reason == "length":
        logger.warning(json.dumps({
            "event": "warning",
            "message": "Refined draft may be truncated due to token limit."
        }))
    return refined_text

def generate_newsletter(category_dir: str, categories: list, openai_key: str, anthropic_key: str) -> tuple[str, float]:
    """
    Generate a newsletter from category analyses with specified categories.
    
    Args:
        category_dir (str): Directory containing category JSON files
        categories (list): List of categories to include
        openai_key (str): OpenAI API key
        anthropic_key (str): Anthropic API key
    
    Returns:
        tuple[str, float]: (newsletter_text, final_score)
    """
    try:
        # Set API keys
        openai.api_key = openai_key
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key

        # Load category analyses
        analyses = {}
        categories_lower = [cat.lower() for cat in categories]
        
        for filename in os.listdir(category_dir):
            if not filename.lower().endswith(".json"):
                continue
                
            category_name = os.path.splitext(filename)[0].lower()
            if category_name not in categories_lower:
                continue

            filepath = os.path.join(category_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    original_category = next(cat for cat in categories if cat.lower() == category_name)
                    analysis_text = data.get("analysis")
                    if analysis_text:
                        analyses[original_category] = analysis_text
            except Exception as e:
                logger.error(f"Failed to load {filepath}: {str(e)}")
                continue

        if not analyses:
            raise ValueError("No category analyses found")

        # Generate initial draft
        available_categories = list(analyses.keys())
        content_sections = [f"Category: {cat}\nContent:\n{text}" for cat, text in analyses.items()]
        combined_content = "\n\n".join(content_sections)
        category_sections = "\n".join([f"- {cat}" for cat in available_categories])

        system_prompt = f"""You are creating a daily digest newsletter that synthesizes content from exactly these categories:
{category_sections}

KEY RULES:
1. ONLY include content from the provided source materials
2. NEVER generate content not present in sources
3. ONLY cover these specific categories
4. Maintain original details and facts
5. Group content by these exact category names"""

        user_prompt = f"""Create a multi-category newsletter from ONLY the provided content. For each category:

1. Use only information from that category's source content
2. Do not add any information not present in sources
3. Group under these exact category headings:
{category_sections}
4. STRICTLY maintain 400-500 words per section - this is crucial
5. Use a friendly, engaging tone while maintaining factual accuracy

IMPORTANT LENGTH REQUIREMENT:
- Each section MUST be between 400-500 words
- Current categories requiring 400-500 words each: {category_sections}
- Total length should be {len(analyses) * 450} words approximately

Content to synthesize by category:
{combined_content}"""

        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=4000
        )

        newsletter = response.choices[0].message.content.strip()

        # Evaluate with Claude
        eval_prompt = (
            "You are an AI assistant evaluating a newsletter draft. "
            "Here is the newsletter content:\n\n"
            f"{newsletter}\n\n"
            "You MUST provide:\n"
            "1. A numerical score from 1-10 (you must give a number)\n"
            "2. 2-3 specific suggestions for improving the newsletter\n\n"
            "Your response MUST start with 'Score: ' followed by a number.\n\n"
            "Evaluate based on:\n"
            "- Section lengths (should be 400-500 words each)\n"
            "- Writing quality and engagement\n"
            "- Factual accuracy and detail preservation\n"
            "- Overall structure and flow"
        )

        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-2",
            max_tokens=1000,
            temperature=0.0,
            messages=[{"role": "user", "content": eval_prompt}]
        )
        
        eval_content = response.content[0].text if response.content else ""
        score_match = re.search(r'Score:\s*(\d+(?:\.\d+)?)', eval_content, re.IGNORECASE)
        score = float(score_match.group(1)) if score_match else 5.0

        return newsletter, score

    except Exception as e:
        logger.error(f"Newsletter generation failed: {str(e)}")
        raise

def main():
    logger.info(json.dumps({"event": "start_newsletter_generation"}))

    # Check API keys are available
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    
    if not openai_key or not anthropic_key:
        logger.error(json.dumps({
            "event": "error",
            "message": "API keys not found in .env.local. Please set OPENAI_API_KEY and ANTHROPIC_API_KEY in .env.local file."
        }))
        return

    # Set the API keys
    openai.api_key = openai_key
    
    # Step 1: Read category preferences with selected categories
    category_dir = "outputs/category_reports"
    category_analyses = load_category_analyses(category_dir, SELECTED_CATEGORIES)
    
    if not category_analyses:
        logger.error(json.dumps({
            "event": "error",
            "message": "No category analyses found. Aborting newsletter generation."
        }))
        return
        
    logger.info(json.dumps({
        "event": "categories_loaded",
        "count": len(category_analyses),
        "categories": list(category_analyses.keys())
    }))

    # Step 2: Generate initial draft using GPT-4
    try:
        initial_draft = generate_newsletter_draft(category_analyses)
    except Exception as e:
        # If generation fails, abort
        logger.error(json.dumps({
            "event": "error",
            "message": "Initial draft generation failed, aborting.",
            "error": str(e)
        }))
        return

    # Step 3: Evaluate the draft using Claude
    try:
        score, suggestions = evaluate_newsletter(initial_draft)
    except Exception as e:
        logger.error(json.dumps({
            "event": "error",
            "message": "Evaluation of initial draft failed, aborting.",
            "error": str(e)
        }))
        return

    # Log the initial evaluation results
    logger.info(json.dumps({
        "event": "initial_evaluation",
        "overall_score": score
    }))

    best_draft = initial_draft
    best_score = score if score is not None else -1  # if score is None, treat as -1

    # Step 4: Iterate to improve the newsletter
    num_iterations = 3  # e.g., perform 3 refinement rounds
    for i in range(1, num_iterations + 1):
        logger.info(json.dumps({
            "event": "iteration_start",
            "iteration": i
        }))

        # Refine the draft with GPT-4 using Claude's feedback
        try:
            refined_draft = refine_newsletter(best_draft, suggestions)
        except Exception as e:
            logger.error(json.dumps({
                "event": "error",
                "message": f"Refinement iteration {i} failed, aborting further iterations.",
                "error": str(e)
            }))
            break  # exit the loop on failure

        # Evaluate the refined draft
        try:
            score, suggestions = evaluate_newsletter(refined_draft)
        except Exception as e:
            logger.error(json.dumps({
                "event": "error",
                "message": f"Evaluation of draft in iteration {i} failed, stopping iterations.",
                "error": str(e)
            }))
            break

        # Log the results of this iteration
        logger.info(json.dumps({
            "event": "iteration_evaluation",
            "iteration": i,
            "overall_score": score
        }))

        # If we got an improvement (or if previous score was None)
        if score is not None and (best_score is None or score > best_score):
            best_score = score
            best_draft = refined_draft
            logger.info(json.dumps({
                "event": "new_best_draft",
                "iteration": i,
                "best_score": best_score
            }))
        else:
            # If no improvement, we could decide to stop early, but as per instructions we continue all iterations
            pass

    # Step 5: Save final output (best performing newsletter draft) to newsletter.txt
    try:
        with open("newsletter.txt", "w", encoding="utf-8") as f:
            f.write(best_draft)
        logger.info(json.dumps({
            "event": "newsletter_saved",
            "file": "newsletter.txt",
            "best_score": best_score
        }))
    except Exception as e:
        logger.error(json.dumps({
            "event": "error",
            "message": "Failed to save newsletter to file.",
            "error": str(e)
        }))

    logger.info(json.dumps({"event": "end_newsletter_generation"}))

if __name__ == "__main__":
    main()
