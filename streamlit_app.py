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
        """Process unprocessed articles with AI summarization"""
        if not ANTHROPIC_AVAILABLE or not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("Anthropic not available for processing")
            return 0
        
        try:
            from ai_service import summarize_article
            
            unprocessed = self.execute_query(
                "SELECT id, title, content FROM articles WHERE processed = 0 AND content IS NOT NULL",
                fetch=True
            )
            
            processed_count = 0
            for article_id, title, content in unprocessed:
                if len(content.strip()) < 100:
                    continue
                
                try:
                    summary, key_points = summarize_article(content, title)
                    
                    if summary and key_points:
                        self.execute_query(
                            "UPDATE articles SET summary = ?, key_points = ?, processed = 1 WHERE id = ?",
                            (summary, key_points, article_id)
                        )
                        processed_count += 1
                        time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Error processing article {title}: {e}")
            
            logger.info(f"Processed {processed_count} articles with AI")
            return processed_count
            
        except ImportError:
            logger.error("ai_service module not available")
            return 0

# Initialize database
@st.cache_resource
def get_database():
    return BlogMonitorDB()

def test_connections():
    """Test all service connections"""
    results = {}
    
    # Test Anthropic
    if ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            from ai_service import test_anthropic_connection
            success, message = test_anthropic_connection()
            results['anthropic'] = {'status': success, 'message': message}
        except Exception as e:
            results['anthropic'] = {'status': False, 'message': str(e)}
    else:
        results['anthropic'] = {'status': False, 'message': 'API key not configured'}
    
    # Test scraping capability
    results['scraping'] = {
        'status': SCRAPING_AVAILABLE, 
        'message': 'Web scraping libraries available' if SCRAPING_AVAILABLE else 'Missing libraries'
    }
    
    # Test email
    email_configured = bool(os.environ.get("EMAIL_ADDRESS") and os.environ.get("EMAIL_PASSWORD"))
    results['email'] = {
        'status': email_configured,
        'message': 'Email configured' if email_configured else 'Email not configured'
    }
    
    # Test Twilio
    twilio_configured = bool(os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_AUTH_TOKEN"))
    results['twilio'] = {
        'status': twilio_configured,
        'message': 'Twilio configured' if twilio_configured else 'Twilio not configured'
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
            if ANTHROPIC_AVAILABLE:
                with st.spinner("Processing with AI..."):
                    count = db.process_articles_with_ai()
                    if count > 0:
                        st.success(f"Processed {count} articles!")
                        st.rerun()
                    else:
                        st.info("No articles to process")
            else:
                st.error("Anthropic not available")
    
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
    
    # Recent articles
    st.subheader("Recent Articles")
    recent_articles = db.execute_query(
        "SELECT title, source, url, summary, scraped_date FROM articles ORDER BY scraped_date DESC LIMIT 5",
        fetch=True
    )
    
    for article in recent_articles:
        title, source, url, summary, scraped_date = article
        
        with st.expander(f"{title} ({source})"):
            st.markdown(f"**Scraped:** {scraped_date}")
            if summary:
                st.markdown(f"**Summary:** {summary[:300]}...")
            st.markdown(f"[Read Full Article]({url})")

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
    
    # Connection tests
    st.subheader("Service Tests")
    
    if st.button("🧪 Test All Connections"):
        with st.spinner("Testing connections..."):
            results = test_connections()
            
            for service, result in results.items():
                status_icon = "✅" if result['status'] else "❌"
                st.markdown(f"{status_icon} **{service.title()}**: {result['message']}")
    
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
    """Show articles with filtering"""
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
    query = "SELECT title, source, url, summary, key_points, processed FROM articles WHERE 1=1"
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
    
    query += " ORDER BY scraped_date DESC LIMIT 20"
    
    articles = db.execute_query(query, params, fetch=True)
    
    # Display articles
    for article in articles:
        title, source, url, summary, key_points, processed = article
        
        with st.expander(f"{'✅' if processed else '❌'} {title} ({source})"):
            st.markdown(f"**URL:** [Link]({url})")
            
            if summary:
                st.markdown("**Summary:**")
                st.markdown(summary)
            
            if key_points:
                st.markdown("**Key Points:**")
                st.markdown(key_points)

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
