import os
import logging
from anthropic import Anthropic
from datetime import datetime
import re

logger = logging.getLogger(__name__)

# Initialize Anthropic client
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

def clean_text(text):
    """Clean text to remove problematic characters"""
    if not text:
        return text
    
    # Remove control characters that break JSON
    cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text)
    # Replace multiple spaces with single space
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def summarize_article(content, title=""):
    """
    Provide analysis of cybersecurity articles - simplified version
    """
    if not anthropic_client:
        logger.error("Anthropic client not initialized")
        return None, None
    
    try:
        # Limit content length
        if len(content) > 8000:
            content = content[:8000] + "..."
        
        # Simple prompt that avoids JSON formatting issues
        prompt = f"""Analyze this cybersecurity article for a security analyst:

Title: {title}

Content: {content}

Please provide:
1. A 2-3 paragraph executive summary
2. 3-5 key takeaways for cybersecurity professionals
3. Technical details worth noting
4. Actionable items for implementation
5. Relevance score (1-10) for cybersecurity analysts

Format your response as plain text, not JSON."""
        
        # Try multiple models
        models = ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]
        
        for model in models:
            try:
                response = anthropic_client.messages.create(
                    model=model,
                    max_tokens=1500,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                response_text = response.content[0].text
                
                # Clean the response
                cleaned_response = clean_text(response_text)
                
                # Parse the plain text response
                summary = ""
                key_points = ""
                
                # Extract sections from the response
                lines = cleaned_response.split('\n')
                current_section = ""
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Look for section headers
                    if any(keyword in line.lower() for keyword in ['summary', 'executive']):
                        current_section = "summary"
                        continue
                    elif any(keyword in line.lower() for keyword in ['takeaway', 'key points', 'insights']):
                        current_section = "takeaways"
                        key_points += "\n🎯 **KEY TAKEAWAYS:**\n"
                        continue
                    elif any(keyword in line.lower() for keyword in ['technical', 'details']):
                        current_section = "technical"
                        key_points += "\n🔧 **TECHNICAL DETAILS:**\n"
                        continue
                    elif any(keyword in line.lower() for keyword in ['actionable', 'action', 'implementation']):
                        current_section = "actionable"
                        key_points += "\n✅ **ACTIONABLE ITEMS:**\n"
                        continue
                    elif any(keyword in line.lower() for keyword in ['relevance', 'score']):
                        current_section = "relevance"
                        key_points += "\n📊 **RELEVANCE SCORE:**\n"
                        continue
                    
                    # Add content to appropriate section
                    if current_section == "summary":
                        summary += line + " "
                    elif current_section in ["takeaways", "technical", "actionable", "relevance"]:
                        if line.startswith(('•', '-', '1.', '2.', '3.', '4.', '5.')):
                            key_points += f"• {line.lstrip('•-123456789. ')}\n"
                        else:
                            key_points += f"{line}\n"
                
                # Fallback if parsing didn't work well
                if not summary:
                    summary = f"Analysis of {title}: " + cleaned_response[:300] + "..."
                
                if not key_points:
                    key_points = f"🤖 **ANALYSIS:**\n{cleaned_response[:800]}...\n\n📊 **STATUS:** Analysis completed successfully"
                
                logger.info(f"Successfully analyzed using {model}: {title}")
                return summary.strip(), key_points.strip()
                
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}")
                continue
        
        logger.error("All models failed")
        return None, None
        
    except Exception as e:
        logger.error(f"Error in analysis: {e}")
        return None, None

def test_anthropic_connection():
    """Test Anthropic connection"""
    if not anthropic_client:
        return False, "Anthropic API key not configured"
    
    try:
        response = anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=50,
            messages=[{"role": "user", "content": "Hello, test connection"}]
        )
        return True, f"Connection successful: {response.content[0].text[:50]}..."
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

# Compatibility functions for Flask mode
def get_db():
    try:
        from app import db
        return db
    except (ImportError, RuntimeError):
        return None

def get_article_model():
    try:
        from models import Article
        return Article
    except ImportError:
        return None

def process_new_articles():
    """Process unprocessed articles"""
    db = get_db()
    Article = get_article_model()
    
    if not db or not Article:
        return 0
    
    unprocessed_articles = Article.query.filter_by(processed=False).all()
    processed_count = 0
    
    for article in unprocessed_articles:
        if not article.content or len(article.content.strip()) < 200:
            article.processed = True
            continue
        
        try:
            summary, key_points = summarize_article(article.content, article.title)
            
            if summary and key_points:
                article.summary = summary
                article.key_points = key_points
                article.processed = True
                processed_count += 1
            else:
                article.processed = True  # Mark as processed to avoid retry loops
            
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error processing {article.title}: {e}")
            article.processed = True
            db.session.commit()
    
    return processed_count

def reprocess_article(article_id, db_instance=None):
    """Reprocess a single article"""
    if db_instance:
        article_data = db_instance.execute_query(
            "SELECT title, content FROM articles WHERE id = ?",
            (article_id,),
            fetch=True
        )
        
        if not article_data:
            return False, "Article not found"
        
        title, content = article_data[0]
        summary, key_points = summarize_article(content, title)
        
        if summary and key_points:
            db_instance.execute_query(
                "UPDATE articles SET summary = ?, key_points = ?, processed = 1 WHERE id = ?",
                (summary, key_points, article_id)
            )
            return True, "Article reprocessed successfully"
        else:
            return False, "Failed to reprocess article"
    
    return False, "Database not available"
