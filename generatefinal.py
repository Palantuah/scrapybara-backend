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
    Use OpenAI GPT-4 to generate a final newsletter from all our categories and their analyses. The newsletter should have clear sections for each category and be engaging and interesting.
    """
    # Construct the prompt for GPT-4
    # We include each category and its analysis. Prompt GPT-4 to write an engaging newsletter covering all categories.
    content_sections = []
    for cat, analysis in analyses.items():
        # Prepare each section input as "Category: [Name]\n[Analysis]"
        section_text = f"Category: {cat}\n{analysis}"
        content_sections.append(section_text)
    combined_content = "\n\n".join(content_sections)

    user_prompt = (
        "You are a seasoned newsletter writer. Using the information provided for each category, "
        "create an engaging, well-structured newsletter. The newsletter should have clear sections for each category, "
        "use a friendly, human-like tone, and keep each section interesting and mostly factual each section should be 400-500 words. "
        "Do NOT include any code, JSON, or markdown formatting in the output; just write plain text. \n\n"
        f"Information for the newsletter:\n{combined_content}\n\n"
        "Now please complete the final newsletter."
    )

    messages = [
        {"role": "system", "content": "You are a helpful assistant and expert writer who crafts newsletters."},
        {"role": "user", "content": user_prompt}
    ]
    try:
        logger.info(json.dumps({"event": "draft_generation_start"}))
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
    except Exception as e:
        # Log and re-raise the error if GPT-4 API call fails
        logger.error(json.dumps({
            "event": "error",
            "stage": "draft_generation",
            "message": "OpenAI API call failed",
            "error": str(e)
        }))
        raise

    # Extract the draft text
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
        "Please provide:\n"
        "1. An overall score from 1-10 for the newsletter quality\n"
        "2. 2-3 specific suggestions for improving the newsletter\n\n"
        "Format your response like this:\n"
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

        # Extract score and suggestions using regex
        score = None
        suggestions = eval_content

        # Try to find the score
        score_match = re.search(r'Score:\s*(\d+(?:\.\d+)?)', eval_content, re.IGNORECASE)
        if score_match:
            try:
                score = float(score_match.group(1))
            except ValueError:
                score = None

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
    refine_prompt = (
        "Here is a newsletter draft that needs improvement:\n\n"
        f"{draft}\n\n"
        "And here is feedback for improvement:\n\n"
        f"{feedback}\n\n"
        "Please refine the newsletter draft according to the feedback. "
        "Maintain the engaging tone and clear structure, and address all the suggestions. "
        "Do not include the feedback text in the output, just provide the improved newsletter. "
        "Ensure the final output is in plain text."
    )
    messages = [
        {"role": "system", "content": "You are a skilled writer who can revise content based on critique to improve its quality."},
        {"role": "user", "content": refine_prompt}
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
