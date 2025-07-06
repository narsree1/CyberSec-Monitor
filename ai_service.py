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
    Provide comprehensive analysis of cybersecurity articles for security analysts
    """
    if not anthropic_client:
        logger.error("Anthropic client not initialized - API key missing")
        return None, None
    
    try:
        # Use a more generous content length for Claude Sonnet
        max_content_length = 15000
        if len(content) > max_content_length:
            # Try to keep the most important parts
            content = content[:max_content_length] + "\n\n[Article content truncated for processing]"
        
        prompt = f"""As a cybersecurity expert, analyze this article comprehensively for a cybersecurity analyst. Provide detailed insights that would be valuable for their daily work and strategic understanding.

Article Title: {title}

Article Content:
{content}

Please provide a thorough analysis in JSON format with the following structure:

{{
    "executive_summary": "A comprehensive 3-4 paragraph summary that captures the essence, methodology, and implications of the article",
    "key_takeaways": [
        "Specific, actionable takeaway 1 that a cybersecurity analyst can apply",
        "Technical insight or methodology that can be implemented", 
        "Strategic implication for security programs",
        "Tool, technique, or process mentioned that could be useful",
        "Risk or threat insight that affects security posture"
    ],
    "technical_details": "Detailed explanation of any technical concepts, tools, methodologies, or frameworks discussed",
    "actionable_items": [
        "Specific action item 1 (e.g., 'Implement X tool for Y purpose')",
        "Process improvement suggestion",
        "Investigation technique to adopt",
        "Security control to evaluate or implement"
    ],
    "threat_intelligence": "Any threat intelligence, attack techniques, vulnerabilities, or security risks mentioned",
    "tools_and_resources": "List of tools, frameworks, resources, or references mentioned that could be useful",
    "relevance_score": "Score from 1-10 indicating how relevant this is for a cybersecurity analyst, with brief explanation"
}}

Focus on providing practical, actionable insights that a cybersecurity analyst can use immediately. Include specific details about methodologies, tools, and techniques. Don't summarize - analyze and extract value."""
        
        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",  # Using Sonnet for better analysis
            max_tokens=2000,  # Increased for comprehensive analysis
            temperature=0.2,  # Lower temperature for more focused analysis
            system="You are a senior cybersecurity consultant who specializes in analyzing technical articles and extracting actionable insights for cybersecurity analysts. Always provide comprehensive, detailed analysis in valid JSON format.",
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
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract the JSON from the response
            import re
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                raise
        
        # Format the comprehensive summary
        summary = result.get("executive_summary", "")
        
        # Format key takeaways and other sections
        sections = []
        
        if result.get("key_takeaways"):
            sections.append("🎯 **KEY TAKEAWAYS:**")
            for takeaway in result["key_takeaways"]:
                sections.append(f"• {takeaway}")
            sections.append("")
        
        if result.get("technical_details"):
            sections.append("🔧 **TECHNICAL DETAILS:**")
            sections.append(result["technical_details"])
            sections.append("")
        
        if result.get("actionable_items"):
            sections.append("✅ **ACTIONABLE ITEMS:**")
            for item in result["actionable_items"]:
                sections.append(f"• {item}")
            sections.append("")
        
        if result.get("threat_intelligence"):
            sections.append("🚨 **THREAT INTELLIGENCE:**")
            sections.append(result["threat_intelligence"])
            sections.append("")
        
        if result.get("tools_and_resources"):
            sections.append("🛠️ **TOOLS & RESOURCES:**")
            sections.append(result["tools_and_resources"])
            sections.append("")
        
        if result.get("relevance_score"):
            sections.append(f"📊 **RELEVANCE SCORE:** {result['relevance_score']}")
        
        key_points = "\n".join(sections)
        
        return summary, key_points
        
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing Claude JSON response: {e}")
        logger.error(f"Raw response: {response_text[:500]}...")
        return None, None
    except Exception as e:
        logger.error(f"Error calling Claude API: {e}")
        return None, None

def process_new_articles():
    """Process unprocessed articles for comprehensive analysis"""
    logger.info("Processing new articles for comprehensive analysis...")
    
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
            if not article.content or len(article.content.strip()) < 200:
                logger.warning(f"Skipping article with insufficient content: {article.title}")
                article.processed = True
                continue
            
            logger.info(f"Processing article: {article.title}")
            
            # Generate comprehensive analysis
            summary, key_points = summarize_article(article.content, article.title)
            
            if summary and key_points:
                article.summary = summary
                article.key_points = key_points
                article.processed = True
                processed_count += 1
                logger.info(f"Successfully processed: {article.title}")
            else:
                logger.error(f"Failed to generate analysis for: {article.title}")
                # Don't mark as processed if it's a rate limit issue
                if summary is None and key_points is None:
                    # Likely an API error, don't mark as processed
                    continue
                else:
                    article.processed = True
            
            db.session.commit()
            
            # Add delay to avoid rate limits
            import time
            time.sleep(2)  # Increased delay for Sonnet
            
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

def process_single_article_comprehensive(article_id, title, content):
    """Process a single article with comprehensive analysis"""
    if not content or len(content.strip()) < 200:
        return None, None
    
    logger.info(f"Processing single article: {title}")
    
    try:
        summary, key_points = summarize_article(content, title)
        
        if summary and key_points:
            logger.info(f"Successfully analyzed: {title}")
            return summary, key_points
        else:
            logger.error(f"Failed to analyze: {title}")
            return None, None
            
    except Exception as e:
        logger.error(f"Error analyzing article {title}: {e}")
        return None, None

def test_anthropic_connection():
    """Test Anthropic API connection with comprehensive output"""
    if not anthropic_client:
        return False, "Anthropic API key not configured"
    
    try:
        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=100,
            messages=[{"role": "user", "content": "Hello, this is a test of the cybersecurity article analysis system. Please confirm you can provide detailed technical analysis."}]
        )
        return True, f"Claude Sonnet connection successful: {response.content[0].text[:100]}..."
    except Exception as e:
        return False, f"Claude connection failed: {str(e)}"

def reprocess_article(article_id, db_instance=None):
    """Reprocess a specific article with enhanced analysis"""
    if db_instance:
        # For Streamlit usage
        article_data = db_instance.execute_query(
            "SELECT title, content FROM articles WHERE id = ?",
            (article_id,),
            fetch=True
        )
        
        if not article_data:
            return False, "Article not found"
        
        title, content = article_data[0]
        summary, key_points = process_single_article_comprehensive(article_id, title, content)
        
        if summary and key_points:
            db_instance.execute_query(
                "UPDATE articles SET summary = ?, key_points = ?, processed = 1 WHERE id = ?",
                (summary, key_points, article_id)
            )
            return True, "Article reprocessed successfully"
        else:
            return False, "Failed to reprocess article"
    
    return False, "Database not available"
