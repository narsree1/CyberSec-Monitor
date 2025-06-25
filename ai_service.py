import os
import json
import logging
from openai import OpenAI
from app import db
from models import Article
from datetime import datetime

logger = logging.getLogger(__name__)

# Initialize OpenAI client
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY not found in environment variables")

openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def summarize_article(content, title=""):
    """
    Summarize article content using OpenAI GPT-4o
    # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
    do not change this unless explicitly requested by the user
    """
    if not openai_client:
        logger.error("OpenAI client not initialized - API key missing")
        return None, None
    
    try:
        # Truncate content if too long (to avoid token limits)
        max_content_length = 8000
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
        
        prompt = f"""
        Please analyze the following cybersecurity article and provide:
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
        """
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a cybersecurity expert who specializes in summarizing technical articles for other security professionals. Focus on actionable insights, new threats, techniques, and important security implications."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=1000,
            temperature=0.3
        )
        
        result = json.loads(response.choices[0].message.content)
        summary = result.get("summary", "")
        key_points = result.get("key_points", [])
        
        # Convert key_points list to formatted string
        key_points_str = "\n".join([f"• {point}" for point in key_points])
        
        return summary, key_points_str
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing OpenAI JSON response: {e}")
        return None, None
    except Exception as e:
        logger.error(f"Error calling OpenAI API: {e}")
        return None, None

def process_new_articles():
    """Process unprocessed articles for summarization"""
    logger.info("Processing new articles for summarization...")
    
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
                # Don't mark as processed if it's a rate limit issue - leave for retry
                if "rate limit" not in str(summary).lower():
                    article.processed = True
            
            db.session.commit()
            
            # Add delay to avoid rate limits
            import time
            time.sleep(2)
            
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
        from notification_service import send_notifications_for_new_articles
        send_notifications_for_new_articles()
    
    return processed_count

def test_openai_connection():
    """Test OpenAI API connection"""
    if not openai_client:
        return False, "OpenAI API key not configured"
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello, this is a test."}],
            max_tokens=10
        )
        return True, "OpenAI connection successful"
    except Exception as e:
        return False, f"OpenAI connection failed: {str(e)}"
