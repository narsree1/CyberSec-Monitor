import os
import json
import logging
from anthropic import Anthropic
from datetime import datetime

logger = logging.getLogger(__name__)

# Initialize Anthropic client
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    logger.warning("ANTHROPIC_API_KEY not found in environment variables")

anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

def get_db():
    """Get database instance - compatible with both Flask and Streamlit"""
    try:
        # Try Flask app context first
        from app import db
        return db
    except (ImportError, RuntimeError):
        # Fall back to simple database for Streamlit
        return None

def get_article_model():
    """Get Article model - compatible with both Flask and Streamlit"""
    try:
        from models import Article
        return Article
    except ImportError:
        return None

def summarize_article(content, title=""):
    """
    Summarize article content using Claude
    """
    if not anthropic_client:
        logger.error("Anthropic client not initialized - API key missing")
        return None, None
    
    try:
        # Truncate content if too long
        max_content_length = 8000
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
        
        prompt = f"""Please analyze the following cybersecurity article and provide:
1. A concise summary (2-3 paragraphs)
2. Key points that a cybersecurity professional should know (3-5 bullet points)

Article Title: {title}

Article Content:
{content}

Please format your response as JSON with the following structure:
{{
    "summary": "Your summary here",
    "key_points": ["Point 1", "Point 2", "Point 3"]
}}

Focus on actionable insights, new threats, techniques, and important security implications."""
        
        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1000,
            temperature=0.3,
            system="You are a cybersecurity expert who specializes in summarizing technical articles for other security professionals. Always respond with valid JSON format.",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        # Extract content from Claude's response
        response_text = response.content[0].text
        
        # Parse JSON response
        result = json.loads(response_text)
        summary = result.get("summary", "")
        key_points = result.get("key_points", [])
        
        # Convert key_points list to formatted string
        key_points_str = "\n".join([f"• {point}" for point in key_points])
        
        return summary, key_points_str
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing Claude JSON response: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Error calling Claude API: {e}")
        return None, None

def process_new_articles():
    """Process unprocessed articles for summarization"""
    logger.info("Processing new articles for summarization...")
    
    db = get_db()
    Article = get_article_model()
    
    if not db or not Article:
        logger.error("Database or Article model not available")
        return 0
    
    # Get unprocessed articles
    unprocessed_articles = Article.query.filter_by(processed=False).all()
    
    if not unprocessed_articles:
        logger.info("No new articles to process")
        return 0
    
    processed_count = 0
    for article in unprocessed_articles:
        try:
            if not article.content or len(article.content.strip()) < 100:
                logger.warning(f"Skipping article with insufficient content: {article.title}")
                article.processed = True
                continue
            
            logger.info(f"Processing article: {article.title}")
            
            # Generate summary and key points
            summary, key_points = summarize_article(article.content, article.title)
            
            if summary and key_points:
                article.summary = summary
                article.key_points = key_points
                article.processed = True
                processed_count += 1
                logger.info(f"Successfully processed: {article.title}")
            else:
                logger.error(f"Failed to generate summary for: {article.title}")
                # Don't mark as processed if it's a rate limit issue
                if "rate limit" not in str(summary).lower():
                    article.processed = True
            
            db.session.commit()
            
            # Add delay to avoid rate limits
            import time
            time.sleep(1)
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error processing article {article.title}: {e}")
            # Only mark as processed if it's not a rate limit error
            if "rate limit" not in str(e).lower() and "429" not in str(e):
                article.processed = True
                db.session.commit()
    
    logger.info(f"Processed {processed_count} articles successfully")
    
    # Send notifications for processed articles
    if processed_count > 0:
        try:
            from notification_service import send_notifications_for_new_articles
            send_notifications_for_new_articles()
        except ImportError:
            logger.warning("Notification service not available")
    
    return processed_count

def test_anthropic_connection():
    """Test Anthropic API connection"""
    if not anthropic_client:
        return False, "Anthropic API key not configured"
    
    try:
        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hello, this is a test."}]
        )
        return True, "Claude connection successful"
    except Exception as e:
        return False, f"Claude connection failed: {str(e)}"
