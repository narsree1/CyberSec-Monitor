import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import sqlite3
import logging
import threading
import time
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Streamlit page
st.set_page_config(
    page_title="Cybersecurity Blog Monitor",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Set environment variables from Streamlit secrets
if hasattr(st, 'secrets'):
    try:
        for key, value in st.secrets.items():
            if isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    os.environ[sub_key] = str(sub_value)
            else:
                os.environ[key] = str(value)
    except Exception as e:
        st.warning(f"Could not load secrets: {e}")

# Check for required imports
MISSING_IMPORTS = []
ANTHROPIC_AVAILABLE = False
SCRAPING_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    MISSING_IMPORTS.append("Anthropic")

try:
    import requests
    import feedparser
    import trafilatura
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    MISSING_IMPORTS.append("Web scraping libraries")

# Custom CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1f2937 0%, #374151 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 2rem;
        color: white;
    }
    .metric-card {
        background: #374151;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #3b82f6;
        color: white;
    }
    .article-card {
        background: #1f2937;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        border-left: 4px solid #10b981;
        color: white;
    }
    .status-good { color: #10b981; }
    .status-bad { color: #ef4444; }
</style>
""", unsafe_allow_html=True)

class BlogMonitorDB:
    """Enhanced database handler with background processing"""
    
    def __init__(self, db_path="blog_monitor.db"):
        self.db_path = db_path
        self.init_db()
        self._last_scrape = None
        
    def init_db(self):
        """Initialize database with all required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create articles table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            content TEXT,
            summary TEXT,
            key_points TEXT,
            published_date TEXT,
            scraped_date TEXT DEFAULT CURRENT_TIMESTAMP,
            processed INTEGER DEFAULT 0,
            notification_sent INTEGER DEFAULT 0
        )
        ''')
        
        # Create sources table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS blog_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            rss_url TEXT,
            scrape_type TEXT DEFAULT 'rss',
            active INTEGER DEFAULT 1,
            created_date TEXT DEFAULT CURRENT_TIMESTAMP,
            last_scraped TEXT
        )
        ''')
        
        # Create notification settings table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_enabled INTEGER DEFAULT 1,
            email_address TEXT,
            whatsapp_enabled INTEGER DEFAULT 1,
            whatsapp_number TEXT,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Create logs table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS scraping_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            articles_found INTEGER DEFAULT 0,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Insert default sources if none exist
        cursor.execute('SELECT COUNT(*) FROM blog_sources')
        if cursor.fetchone()[0] == 0:
            default_sources = [
                ('Detection Engineering', 'https://www.detectionengineering.net/', None, 'html'),
                ('Rohit Tamma Substack', 'https://rohittamma.substack.com/', 'https://rohittamma.substack.com/feed', 'rss'),
                ('Anton on Security', 'https://medium.com/@anton.on.security', 'https://medium.com/feed/@anton.on.security', 'rss'),
                ('Google Cloud Security', 'https://cloud.google.com/blog/topics/security', None, 'html'),
                ('Detect FYI', 'https://detect.fyi/', None, 'html'),
                ('Dylan H Williams', 'https://medium.com/@dylanhwilliams', 'https://medium.com/feed/@dylanhwilliams', 'rss'),
            ]
            
            cursor.executemany(
                'INSERT INTO blog_sources (name, url, rss_url, scrape_type) VALUES (?, ?, ?, ?)',
                default_sources
            )
        
        conn.commit()
        conn.close()
    
    def execute_query(self, query, params=None, fetch=False):
        """Execute database query safely"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            if fetch:
                result = cursor.fetchall()
                conn.close()
                return result
            
            conn.commit()
            conn.close()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Database error: {e}")
            return [] if fetch else 0
    
    def scrape_rss_feed(self, source):
        """Scrape RSS feed for articles"""
        if not SCRAPING_AVAILABLE:
            return []
        
        articles = []
        try:
            feed = feedparser.parse(source['rss_url'])
            
            for entry in feed.entries[:5]:  # Limit to 5 recent articles
                # Check if article already exists
                existing = self.execute_query(
                    "SELECT COUNT(*) FROM articles WHERE url = ?", 
                    (entry.link,), 
                    fetch=True
                )[0][0]
                
                if existing > 0:
                    continue
                
                # Get content using trafilatura
                content = None
                try:
                    downloaded = trafilatura.fetch_url(entry.link)
                    if downloaded:
                        content = trafilatura.extract(downloaded)
                except Exception as e:
                    logger.error(f"Error extracting content from {entry.link}: {e}")
                
                # Parse published date
                published_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_date = datetime(*entry.published_parsed[:6]).isoformat()
                
                articles.append({
                    'title': entry.title,
                    'url': entry.link,
                    'source': source['name'],
                    'content': content,
                    'published_date': published_date
                })
                
        except Exception as e:
            logger.error(f"Error scraping RSS for {source['name']}: {e}")
        
        return articles
    
    def scrape_website(self, source):
        """Scrape website for article links"""
        if not SCRAPING_AVAILABLE:
            return []
        
        articles = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(source['url'], headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find article links
            article_links = set()
            selectors = [
                'a[href*="/blog/"]', 'a[href*="/post/"]', 'a[href*="/article/"]',
                'h2 a', 'h3 a', '.post-title a', '.article-title a'
            ]
            
            for selector in selectors:
                links = soup.select(selector)
                for link in links[:10]:
                    href = link.get('href')
                    if href:
                        if href.startswith('/'):
                            href = source['url'].rstrip('/') + href
                        if href.startswith('http'):
                            article_links.add(href)
            
            # Process article links
            for url in list(article_links)[:3]:  # Limit to 3 articles
                try:
                    # Check if exists
                    existing = self.execute_query(
                        "SELECT COUNT(*) FROM articles WHERE url = ?", 
                        (url,), 
                        fetch=True
                    )[0][0]
                    
                    if existing > 0:
                        continue
                    
                    # Get content
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        content = trafilatura.extract(downloaded)
                        if content and len(content.strip()) > 100:
                            # Extract title
                            title = content.split('\n')[0][:200] if content else url.split('/')[-1]
                            
                            articles.append({
                                'title': title,
                                'url': url,
                                'source': source['name'],
                                'content': content,
                                'published_date': None
                            })
                    
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Error processing {url}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error scraping website {source['name']}: {e}")
        
        return articles
    
    def scrape_all_sources(self):
        """Scrape all active sources"""
        logger.info("Starting scraping of all sources...")
        
        sources = self.execute_query(
            "SELECT name, url, rss_url, scrape_type FROM blog_sources WHERE active = 1",
            fetch=True
        )
        
        total_articles = 0
        
        for source_row in sources:
            name, url, rss_url, scrape_type = source_row
            source = {
                'name': name,
                'url': url,
                'rss_url': rss_url,
                'scrape_type': scrape_type
            }
            
            try:
                articles = []
                
                if scrape_type == 'rss' and rss_url:
                    articles = self.scrape_rss_feed(source)
                else:
                    articles = self.scrape_website(source)
                
                # Save articles
                for article in articles:
                    try:
                        self.execute_query(
                            """INSERT INTO articles (title, url, source, content, published_date) 
                               VALUES (?, ?, ?, ?, ?)""",
                            (article['title'], article['url'], article['source'], 
                             article['content'], article['published_date'])
                        )
                        total_articles += 1
                        logger.info(f"Saved: {article['title']}")
                    except Exception as e:
                        logger.error(f"Error saving article: {e}")
                
                # Log scraping result
                self.execute_query(
                    "INSERT INTO scraping_logs (source, status, message, articles_found) VALUES (?, ?, ?, ?)",
                    (name, 'success' if articles else 'no_new_articles', 
                     f"Found {len(articles)} new articles", len(articles))
                )
                
                time.sleep(2)  # Rate limiting between sources
                
            except Exception as e:
                logger.error(f"Error scraping {name}: {e}")
                self.execute_query(
                    "INSERT INTO scraping_logs (source, status, message, articles_found) VALUES (?, ?, ?, ?)",
                    (name, 'error', str(e), 0)
                )
        
        logger.info(f"Scraping completed. Total new articles: {total_articles}")
        self._last_scrape = datetime.now()
        
        # Process articles with AI if available
        if total_articles > 0 and ANTHROPIC_AVAILABLE:
            self.process_articles_with_ai()
        
        return total_articles
    
    def process_articles_with_ai(self):
        """Process unprocessed articles with comprehensive AI analysis"""
        if not ANTHROPIC_AVAILABLE or not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("Anthropic not available for processing")
            return 0
        
        try:
            # Import here to avoid issues
            import sys
            sys.path.append('.')
            
            # Try to import the AI service
            try:
                from ai_service import summarize_article
            except ImportError:
                # If import fails, define a simple version inline
                logger.warning("Could not import ai_service, using inline version")
                return self.process_articles_inline()
            
            unprocessed = self.execute_query(
                "SELECT id, title, content FROM articles WHERE processed = 0 AND content IS NOT NULL AND length(trim(content)) > 200",
                fetch=True
            )
            
            if not unprocessed:
                logger.info("No unprocessed articles found")
                return 0
            
            processed_count = 0
            for article_id, title, content in unprocessed:
                try:
                    logger.info(f"Processing with AI: {title}")
                    summary, key_points = summarize_article(content, title)
                    
                    if summary and key_points:
                        self.execute_query(
                            "UPDATE articles SET summary = ?, key_points = ?, processed = 1 WHERE id = ?",
                            (summary, key_points, article_id)
                        )
                        processed_count += 1
                        logger.info(f"Successfully processed: {title}")
                        time.sleep(2)  # Rate limiting
                    else:
                        logger.error(f"No analysis generated for: {title}")
                        # Mark as processed to avoid retry loops
                        self.execute_query(
                            "UPDATE articles SET processed = 1 WHERE id = ?",
                            (article_id,)
                        )
                    
                except Exception as e:
                    logger.error(f"Error processing article {title}: {e}")
                    # Mark as processed on error to avoid retry loops
                    self.execute_query(
                        "UPDATE articles SET processed = 1 WHERE id = ?",
                        (article_id,)
                    )
            
            logger.info(f"Processed {processed_count} articles with comprehensive AI analysis")
            return processed_count
            
        except Exception as e:
            logger.error(f"Error in AI processing: {e}")
            return 0
    
    def process_articles_inline(self):
        """Inline AI processing when ai_service import fails"""
        if not ANTHROPIC_AVAILABLE or not os.environ.get("ANTHROPIC_API_KEY"):
            return 0
        
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            
            # Try different models
            models_to_try = [
                "claude-3-5-sonnet-20241022",
                "claude-3-5-sonnet-20240620", 
                "claude-3-haiku-20240307"
            ]
            
            working_model = None
            for model in models_to_try:
                try:
                    test_response = client.messages.create(
                        model=model,
                        max_tokens=10,
                        messages=[{"role": "user", "content": "test"}]
                    )
                    working_model = model
                    logger.info(f"Using model: {model}")
                    break
                except Exception as e:
                    logger.warning(f"Model {model} not available: {e}")
                    continue
            
            if not working_model:
                logger.error("No working Claude models found")
                return 0
            
            unprocessed = self.execute_query(
                "SELECT id, title, content FROM articles WHERE processed = 0 AND content IS NOT NULL",
                fetch=True
            )
            
            processed_count = 0
            for article_id, title, content in unprocessed:
                if len(content.strip()) < 200:
                    # Mark short articles as processed
                    self.execute_query(
                        "UPDATE articles SET processed = 1 WHERE id = ?",
                        (article_id,)
                    )
                    continue
                
                try:
                    # Simple analysis prompt
                    prompt = f"""Analyze this cybersecurity article for a security analyst:

Title: {title}
Content: {content[:8000]}

Provide a JSON response with:
{{
    "summary": "2-3 paragraph executive summary",
    "key_takeaways": ["takeaway 1", "takeaway 2", "takeaway 3"],
    "technical_details": "technical explanation",
    "actionable_items": ["action 1", "action 2"],
    "relevance_score": "score 1-10 with explanation"
}}"""
                    
                    response = client.messages.create(
                        model=working_model,
                        max_tokens=1500,
                        temperature=0.3,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    
                    response_text = response.content[0].text
                    
                    # Clean response text to handle control characters
                    import re
                    cleaned_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', response_text)
                    
                    # Try to parse JSON
                    try:
                        import json
                        result = json.loads(cleaned_text)
                        
                        summary = result.get("summary", "Analysis completed")
                        
                        # Format key points
                        sections = []
                        if result.get("key_takeaways"):
                            sections.append("🎯 **KEY TAKEAWAYS:**")
                            for item in result["key_takeaways"]:
                                sections.append(f"• {item}")
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
                        
                        if result.get("relevance_score"):
                            sections.append(f"📊 **RELEVANCE SCORE:** {result['relevance_score']}")
                        
                        key_points = "\n".join(sections)
                        
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON parsing failed for {title}: {e}")
                        
                        # Try to extract key information manually
                        summary_match = re.search(r'"summary":\s*"([^"]*)"', cleaned_text)
                        summary = summary_match.group(1) if summary_match else f"AI Analysis of: {title}"
                        
                        # Create a simple analysis from the raw response
                        key_points = f"""🤖 **AI ANALYSIS:**
{cleaned_text[:800]}...

🎯 **EXTRACTED INSIGHTS:**
• Analysis completed successfully
• See summary above for key details
• Article contains cybersecurity-relevant information

📊 **STATUS:** Analysis completed with text extraction"""
                    
                    # Save results
                    self.execute_query(
                        "UPDATE articles SET summary = ?, key_points = ?, processed = 1 WHERE id = ?",
                        (summary, key_points, article_id)
                    )
                    
                    processed_count += 1
                    logger.info(f"Processed: {title}")
                    time.sleep(2)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Error processing {title}: {e}")
                    # Mark as processed to avoid retry
                    self.execute_query(
                        "UPDATE articles SET processed = 1 WHERE id = ?",
                        (article_id,)
                    )
            
            return processed_count
            
        except Exception as e:
            logger.error(f"Inline processing error: {e}")
            return 0
    
    def reprocess_single_article(self, article_id):
        """Reprocess a single article with enhanced analysis"""
        if not ANTHROPIC_AVAILABLE or not os.environ.get("ANTHROPIC_API_KEY"):
            return False, "Anthropic not available"
        
        try:
            from ai_service import reprocess_article
            return reprocess_article(article_id, self)
        except ImportError:
            return False, "AI service not available"

# Initialize database
@st.cache_resource
def get_database():
    return BlogMonitorDB()

def test_connections():
    """Test all service connections with detailed feedback"""
    results = {}
    
    # Test Anthropic with comprehensive testing
    if ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from ai_service import test_anthropic_connection
            success, message = test_anthropic_connection()
            results['anthropic'] = {
                'status': success, 
                'message': message,
                'model': 'Claude Sonnet (Comprehensive Analysis)' if success else 'Connection Failed'
            }
        except Exception as e:
            results['anthropic'] = {
                'status': False, 
                'message': str(e),
                'model': 'Error'
            }
    else:
        results['anthropic'] = {
            'status': False, 
            'message': 'API key not configured',
            'model': 'Not Available'
        }
    
    # Test scraping capability
    results['scraping'] = {
        'status': SCRAPING_AVAILABLE, 
        'message': 'Web scraping libraries available' if SCRAPING_AVAILABLE else 'Missing libraries',
        'libraries': 'requests, beautifulsoup4, feedparser, trafilatura' if SCRAPING_AVAILABLE else 'Missing'
    }
    
    # Test email
    email_configured = bool(os.environ.get("EMAIL_ADDRESS") and os.environ.get("EMAIL_PASSWORD"))
    results['email'] = {
        'status': email_configured,
        'message': 'Email configured' if email_configured else 'Email not configured',
        'smtp': os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    }
    
    # Test Twilio
    twilio_configured = bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN"))
    results['twilio'] = {
        'status': twilio_configured,
        'message': 'Twilio configured' if twilio_configured else 'Twilio not configured',
        'service': 'WhatsApp notifications' if twilio_configured else 'Not available'
    }
    
    return results

def main():
    """Main application"""
    st.sidebar.title("🔒 Blog Monitor")
    
    # Show dependency status in sidebar
    if MISSING_IMPORTS:
        st.sidebar.error(f"Missing: {', '.join(MISSING_IMPORTS)}")
    else:
        st.sidebar.success("All dependencies loaded")
    
    page = st.sidebar.selectbox(
        "Navigation",
        ["Dashboard", "System Status", "Articles", "Sources", "Settings"]
    )
    
    db = get_database()
    
    if page == "Dashboard":
        show_dashboard(db)
    elif page == "System Status":
        show_system_status(db)
    elif page == "Articles":
        show_articles(db)
    elif page == "Sources":
        show_sources(db)
    elif page == "Settings":
        show_settings(db)

def show_dashboard(db):
    """Show main dashboard"""
    st.markdown('<div class="main-header"><h1>🔒 Cybersecurity Blog Monitor</h1><p>AI-powered monitoring of cybersecurity blogs</p></div>', unsafe_allow_html=True)
    
    # Manual scraping button
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("🔄 Scrape Now", type="primary"):
            if SCRAPING_AVAILABLE:
                with st.spinner("Scraping articles..."):
                    count = db.scrape_all_sources()
                    if count > 0:
                        st.success(f"Found {count} new articles!")
                        st.rerun()
                    else:
                        st.info("No new articles found")
            else:
                st.error("Scraping libraries not available")
    
    with col2:
        if st.button("🤖 Process AI", type="secondary"):
            if ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
                with st.spinner("Processing with AI..."):
                    # First check if there are articles to process
                    unprocessed_count = db.execute_query(
                        "SELECT COUNT(*) FROM articles WHERE processed = 0", 
                        fetch=True
                    )[0][0]
                    
                    if unprocessed_count == 0:
                        st.info("No unprocessed articles found")
                    else:
                        st.info(f"Found {unprocessed_count} articles to process...")
                        count = db.process_articles_with_ai()
                        if count > 0:
                            st.success(f"Processed {count} articles!")
                            st.rerun()
                        else:
                            st.error("Processing failed - check logs")
            else:
                st.error("Anthropic not available - check API key")
    
    with col3:
        # Debug info
        if st.button("🔍 Debug Info"):
            with st.expander("Debug Information", expanded=True):
                # Check unprocessed articles
                unprocessed = db.execute_query(
                    "SELECT id, title, length(content), processed FROM articles ORDER BY id DESC LIMIT 5",
                    fetch=True
                )
                
                st.markdown("**Recent Articles Status:**")
                for article in unprocessed:
                    article_id, title, content_length, processed = article
                    status = "✅ Processed" if processed else "❌ Unprocessed"
                    st.markdown(f"- {title[:50]}... | Content: {content_length} chars | {status}")
                
                # Check API key
                api_key_configured = bool(os.environ.get("ANTHROPIC_API_KEY"))
                st.markdown(f"**API Key Configured:** {'✅' if api_key_configured else '❌'}")
                
                # Check libraries
                st.markdown(f"**Anthropic Available:** {'✅' if ANTHROPIC_AVAILABLE else '❌'}")
                
                if api_key_configured and ANTHROPIC_AVAILABLE:
                    if st.button("🧪 Test Single Article"):
                        # Get first unprocessed article
                        test_article = db.execute_query(
                            "SELECT id, title, content FROM articles WHERE processed = 0 LIMIT 1",
                            fetch=True
                        )
                        
                        if test_article:
                            article_id, title, content = test_article[0]
                            
                            with st.spinner(f"Testing analysis on: {title}"):
                                success, message = db.reprocess_single_article(article_id)
                                if success:
                                    st.success("✅ Test analysis successful!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Test failed: {message}")
                        else:
                            st.info("No unprocessed articles to test")
    
    # Statistics
    stats = {
        'total': db.execute_query("SELECT COUNT(*) FROM articles", fetch=True)[0][0],
        'processed': db.execute_query("SELECT COUNT(*) FROM articles WHERE processed = 1", fetch=True)[0][0],
        'recent': db.execute_query(
            "SELECT COUNT(*) FROM articles WHERE scraped_date >= ?", 
            ((datetime.now() - timedelta(days=7)).isoformat(),), 
            fetch=True
        )[0][0],
        'sources': db.execute_query("SELECT COUNT(*) FROM blog_sources WHERE active = 1", fetch=True)[0][0]
    }
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Articles", stats['total'])
    with col2:
        st.metric("Processed", stats['processed'])
    with col3:
        st.metric("Recent (7d)", stats['recent'])
    with col4:
        st.metric("Active Sources", stats['sources'])
    
    # Recent articles with enhanced display
    st.subheader("📈 Recent Articles")
    recent_articles = db.execute_query(
        "SELECT title, source, url, summary, key_points, processed, scraped_date FROM articles ORDER BY scraped_date DESC LIMIT 5",
        fetch=True
    )
    
    if recent_articles:
        for article in recent_articles:
            title, source, url, summary, key_points, processed, scraped_date = article
            
            with st.container():
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    status_icon = "✅" if processed else "❌"
                    st.markdown(f"**{status_icon} {title}**")
                    st.markdown(f"*Source: {source} | Scraped: {scraped_date}*")
                    
                    if processed and summary:
                        # Show first part of summary
                        preview = summary[:200] + "..." if len(summary) > 200 else summary
                        st.markdown(f"📋 **Summary:** {preview}")
                        
                        # Show if we have comprehensive analysis
                        if key_points and ("🎯" in key_points or "🔧" in key_points):
                            st.markdown("🔍 *Comprehensive cybersecurity analysis available*")
                    elif not processed:
                        st.markdown("🤖 *Ready for AI analysis*")
                
                with col2:
                    st.markdown(f"[📖 Read Full]({url})")
                    if processed:
                        st.markdown("✅ Analyzed")
                    else:
                        st.markdown("⏳ Pending")
                
                st.divider()
    else:
        st.info("No articles found. Click 'Scrape Now' to find cybersecurity articles.")
    
    # Processing stats
    if stats['total'] > 0:
        st.subheader("📊 Processing Statistics")
        
        col1, col2 = st.columns(2)
        
        with col1:
            processing_rate = (stats['processed'] / stats['total']) * 100
            st.metric(
                "Processing Rate", 
                f"{processing_rate:.1f}%",
                help="Percentage of articles that have been analyzed with AI"
            )
        
        with col2:
            unprocessed_count = stats['total'] - stats['processed']
            st.metric(
                "Pending Analysis", 
                unprocessed_count,
                help="Number of articles waiting for AI analysis"
            )

def show_system_status(db):
    """Show system status and tests"""
    st.header("🔧 System Status")
    
    # Environment check
    st.subheader("Environment Variables")
    env_vars = [
        ("ANTHROPIC_API_KEY", "🤖 AI Processing"),
        ("EMAIL_ADDRESS", "📧 Email Notifications"),
        ("EMAIL_PASSWORD", "📧 Email Authentication"),
        ("TWILIO_ACCOUNT_SID", "📱 WhatsApp Notifications"),
        ("TWILIO_AUTH_TOKEN", "📱 WhatsApp Authentication")
    ]
    
    for var, description in env_vars:
        status = "✅" if os.environ.get(var) else "❌"
        st.markdown(f"{status} **{var}** - {description}")
    
    # Connection tests with enhanced display
    st.subheader("🔬 Service Tests")
    
    if st.button("🧪 Test All Connections"):
        with st.spinner("Testing connections..."):
            results = test_connections()
            
            st.markdown("### Test Results:")
            
            for service, result in results.items():
                status_icon = "✅" if result['status'] else "❌"
                service_name = service.replace('_', ' ').title()
                
                with st.container():
                    col1, col2 = st.columns([1, 3])
                    
                    with col1:
                        st.markdown(f"**{status_icon} {service_name}**")
                    
                    with col2:
                        st.markdown(f"**Status:** {result['message']}")
                        
                        # Show additional details if available
                        if 'model' in result:
                            st.markdown(f"**Model:** {result['model']}")
                        if 'libraries' in result:
                            st.markdown(f"**Libraries:** {result['libraries']}")
                        if 'smtp' in result:
                            st.markdown(f"**SMTP Server:** {result['smtp']}")
                        if 'service' in result:
                            st.markdown(f"**Service:** {result['service']}")
                    
                    st.divider()
    
    # Quick AI Analysis Test
    st.subheader("🤖 AI Analysis Test")
    
    if ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
        if st.button("🧠 Test AI Analysis"):
            test_content = """
            This is a test cybersecurity article about implementing zero-trust architecture.
            Zero trust is a security framework that requires all users, whether in or outside 
            the organization's network, to be authenticated, authorized, and continuously 
            validated for security configuration and posture before being granted or keeping 
            access to applications and data. This approach helps prevent data breaches and 
            limits internal threat movement.
            """
            
            with st.spinner("Testing AI analysis capabilities..."):
                try:
                    from ai_service import summarize_article
                    summary, key_points = summarize_article(test_content, "Zero Trust Architecture Test")
                    
                    if summary and key_points:
                        st.success("✅ AI Analysis Test Successful!")
                        
                        with st.expander("View Test Analysis Results"):
                            st.markdown("**Summary:**")
                            st.markdown(summary)
                            st.markdown("**Analysis:**")
                            st.markdown(key_points)
                    else:
                        st.error("❌ AI Analysis Test Failed - No results generated")
                        
                except Exception as e:
                    st.error(f"❌ AI Analysis Test Failed: {str(e)}")
    else:
        st.warning("⚠️ AI Analysis not available - Configure ANTHROPIC_API_KEY")
    
    # System Information
    st.subheader("📋 System Information")
    
    system_info = {
        "Python Environment": "Streamlit Cloud",
        "Database": "SQLite (Local)",
        "AI Model": "Claude Sonnet (Anthropic)" if ANTHROPIC_AVAILABLE else "Not Available",
        "Scraping": "Enabled" if SCRAPING_AVAILABLE else "Disabled",
        "Notifications": "Email + WhatsApp" if os.environ.get("EMAIL_ADDRESS") and os.environ.get("TWILIO_ACCOUNT_SID") else "Partial/Disabled"
    }
    
    for key, value in system_info.items():
        st.markdown(f"**{key}:** {value}")
    
    # Performance metrics
    st.subheader("⚡ Performance Metrics")
    
    # Get database stats
    total_articles = db.execute_query("SELECT COUNT(*) FROM articles", fetch=True)[0][0]
    processed_articles = db.execute_query("SELECT COUNT(*) FROM articles WHERE processed = 1", fetch=True)[0][0]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Articles Scraped", total_articles)
    
    with col2:
        st.metric("Articles Analyzed", processed_articles)
    
    with col3:
        processing_rate = (processed_articles / total_articles * 100) if total_articles > 0 else 0
        st.metric("Analysis Rate", f"{processing_rate:.1f}%")
    
    # Recent logs
    st.subheader("Recent Scraping Logs")
    logs = db.execute_query(
        "SELECT source, status, message, articles_found, timestamp FROM scraping_logs ORDER BY timestamp DESC LIMIT 10",
        fetch=True
    )
    
    for log in logs:
        source, status, message, articles_found, timestamp = log
        status_icon = "✅" if status == 'success' else "❌" if status == 'error' else "ℹ️"
        st.markdown(f"{status_icon} **{source}** ({timestamp}): {message}")

def show_articles(db):
    """Show articles with comprehensive analysis display"""
    st.header("📰 Articles")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        sources = ["All"] + [row[0] for row in db.execute_query("SELECT DISTINCT source FROM articles", fetch=True)]
        selected_source = st.selectbox("Source", sources)
    
    with col2:
        status_filter = st.selectbox("Status", ["All", "Processed", "Unprocessed"])
    
    with col3:
        search = st.text_input("Search")
    
    # Build query
    query = "SELECT id, title, source, url, summary, key_points, processed, scraped_date FROM articles WHERE 1=1"
    params = []
    
    if selected_source != "All":
        query += " AND source = ?"
        params.append(selected_source)
    
    if status_filter == "Processed":
        query += " AND processed = 1"
    elif status_filter == "Unprocessed":
        query += " AND processed = 0"
    
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")
    
    query += " ORDER BY scraped_date DESC LIMIT 30"
    
    articles = db.execute_query(query, params, fetch=True)
    
    if not articles:
        st.info("No articles found matching your criteria.")
        return
    
    # Display articles with enhanced formatting
    for article in articles:
        article_id, title, source, url, summary, key_points, processed, scraped_date = article
        
        # Create expandable article card
        status_icon = "✅" if processed else "❌"
        processed_text = "Analyzed" if processed else "Not Analyzed"
        
        with st.expander(f"{status_icon} {title} ({source}) - {processed_text}"):
            # Article metadata
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(f"**Source:** {source}")
                st.markdown(f"**Scraped:** {scraped_date}")
            
            with col2:
                st.markdown(f"[🔗 Read Original]({url})")
            
            with col3:
                if not processed and ANTHROPIC_AVAILABLE:
                    if st.button("🤖 Analyze Now", key=f"analyze_{article_id}"):
                        with st.spinner("Analyzing article..."):
                            success, message = db.reprocess_single_article(article_id)
                            if success:
                                st.success("Article analyzed successfully!")
                                st.rerun()
                            else:
                                st.error(f"Analysis failed: {message}")
                elif processed:
                    if st.button("🔄 Re-analyze", key=f"reanalyze_{article_id}"):
                        with st.spinner("Re-analyzing article..."):
                            success, message = db.reprocess_single_article(article_id)
                            if success:
                                st.success("Article re-analyzed successfully!")
                                st.rerun()
                            else:
                                st.error(f"Re-analysis failed: {message}")
            
            # Show analysis if available
            if processed and summary:
                st.markdown("---")
                
                # Executive Summary
                st.markdown("### 📋 Executive Summary")
                st.markdown(summary)
                
                # Detailed Analysis
                if key_points:
                    st.markdown("### 🔍 Detailed Analysis")
                    
                    # Parse and display the structured key points
                    sections = key_points.split('\n\n')
                    
                    for section in sections:
                        if section.strip():
                            lines = section.strip().split('\n')
                            if lines:
                                # Check if this is a section header
                                if lines[0].startswith('🎯') or lines[0].startswith('🔧') or lines[0].startswith('✅') or lines[0].startswith('🚨') or lines[0].startswith('🛠️') or lines[0].startswith('📊'):
                                    st.markdown(f"**{lines[0]}**")
                                    
                                    # Display the content of this section
                                    for line in lines[1:]:
                                        if line.strip():
                                            if line.startswith('•'):
                                                st.markdown(f"  {line}")
                                            else:
                                                st.markdown(line)
                                else:
                                    # Regular content
                                    for line in lines:
                                        if line.strip():
                                            st.markdown(line)
                            
                            st.markdown("")  # Add spacing between sections
            
            elif not processed:
                st.info("🤖 This article hasn't been analyzed yet. Click 'Analyze Now' to get comprehensive cybersecurity insights.")
            
            else:
                st.warning("⚠️ Analysis data appears to be incomplete. Try re-analyzing this article.")

def show_sources(db):
    """Manage blog sources"""
    st.header("📚 Blog Sources")
    
    # Add new source
    with st.expander("➕ Add New Source"):
        with st.form("add_source"):
            name = st.text_input("Source Name")
            url = st.text_input("Website URL")
            rss_url = st.text_input("RSS Feed URL (optional)")
            scrape_type = st.selectbox("Scraping Method", ["rss", "html"])
            
            if st.form_submit_button("Add Source"):
                if name and url:
                    db.execute_query(
                        "INSERT INTO blog_sources (name, url, rss_url, scrape_type) VALUES (?, ?, ?, ?)",
                        (name, url, rss_url if rss_url else None, scrape_type)
                    )
                    st.success(f"Added source: {name}")
                    st.rerun()
                else:
                    st.error("Please provide both name and URL")
    
    # Display existing sources
    st.subheader("Current Sources")
    sources = db.execute_query(
        "SELECT id, name, url, scrape_type, active, last_scraped FROM blog_sources ORDER BY name",
        fetch=True
    )
    
    for source in sources:
        source_id, name, url, scrape_type, active, last_scraped = source
        
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            
            with col1:
                status_icon = "✅" if active else "❌"
                st.markdown(f"{status_icon} **{name}**")
                st.markdown(f"[{url}]({url})")
            
            with col2:
                st.markdown(f"**Type:** {scrape_type}")
                st.markdown(f"**Last Scraped:** {last_scraped or 'Never'}")
            
            with col3:
                if st.button("Toggle", key=f"toggle_{source_id}"):
                    db.execute_query(
                        "UPDATE blog_sources SET active = ? WHERE id = ?",
                        (1 - active, source_id)
                    )
                    st.rerun()
            
            with col4:
                if st.button("Delete", key=f"delete_{source_id}"):
                    db.execute_query("DELETE FROM blog_sources WHERE id = ?", (source_id,))
                    st.rerun()
            
            st.divider()

def show_settings(db):
    """Manage notification settings"""
    st.header("⚙️ Settings")
    
    # Get current settings
    settings = db.execute_query(
        "SELECT email_enabled, email_address, whatsapp_enabled, whatsapp_number FROM notification_settings LIMIT 1",
        fetch=True
    )
    
    if settings:
        email_enabled, email_address, whatsapp_enabled, whatsapp_number = settings[0]
    else:
        email_enabled, email_address, whatsapp_enabled, whatsapp_number = 1, "", 1, ""
    
    # Email settings
    st.subheader("📧 Email Notifications")
    with st.form("email_settings"):
        new_email_enabled = st.checkbox("Enable Email Notifications", value=bool(email_enabled))
        new_email_address = st.text_input("Email Address", value=email_address or "")
        
        if st.form_submit_button("Save Email Settings"):
            # Update or insert settings
            if settings:
                db.execute_query(
                    "UPDATE notification_settings SET email_enabled = ?, email_address = ?",
                    (int(new_email_enabled), new_email_address)
                )
            else:
                db.execute_query(
                    "INSERT INTO notification_settings (email_enabled, email_address, whatsapp_enabled, whatsapp_number) VALUES (?, ?, 1, '')",
                    (int(new_email_enabled), new_email_address)
                )
            st.success("Email settings saved!")
            st.rerun()
    
    # WhatsApp settings
    st.subheader("📱 WhatsApp Notifications")
    with st.form("whatsapp_settings"):
        new_whatsapp_enabled = st.checkbox("Enable WhatsApp Notifications", value=bool(whatsapp_enabled))
        new_whatsapp_number = st.text_input("WhatsApp Number (with country code)", value=whatsapp_number or "")
        
        if st.form_submit_button("Save WhatsApp Settings"):
            if settings:
                db.execute_query(
                    "UPDATE notification_settings SET whatsapp_enabled = ?, whatsapp_number = ?",
                    (int(new_whatsapp_enabled), new_whatsapp_number)
                )
            else:
                db.execute_query(
                    "INSERT INTO notification_settings (email_enabled, email_address, whatsapp_enabled, whatsapp_number) VALUES (1, '', ?, ?)",
                    (int(new_whatsapp_enabled), new_whatsapp_number)
                )
            st.success("WhatsApp settings saved!")
            st.rerun()
    
    # Environment variables info
    st.subheader("🔑 Required Environment Variables")
    st.info("""
    To enable full functionality, set these environment variables in Streamlit Cloud:
    
    **For AI Processing:**
    - `ANTHROPIC_API_KEY`: Your Anthropic API key
    
    **For Email Notifications:**
    - `EMAIL_ADDRESS`: Your email address
    - `EMAIL_PASSWORD`: Your email app password
    - `SMTP_SERVER`: SMTP server (default: smtp.gmail.com)
    - `SMTP_PORT`: SMTP port (default: 587)
    
    **For WhatsApp Notifications:**
    - `TWILIO_ACCOUNT_SID`: Your Twilio Account SID
    - `TWILIO_AUTH_TOKEN`: Your Twilio Auth Token
    - `TWILIO_PHONE_NUMBER`: Your Twilio phone number
    """)

if __name__ == "__main__":
    main()
