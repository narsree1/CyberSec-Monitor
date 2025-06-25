import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import sys
import sqlite3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Set environment variables from Streamlit secrets if available
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

# Configure Streamlit page
st.set_page_config(
    page_title="Cybersecurity Blog Monitor",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Check for required imports and show appropriate errors
MISSING_IMPORTS = []

try:
    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    FLASK_AVAILABLE = True
except ImportError as e:
    FLASK_AVAILABLE = False
    MISSING_IMPORTS.append("Flask/SQLAlchemy")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    MISSING_IMPORTS.append("OpenAI")

try:
    import requests
    import feedparser
    import trafilatura
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False
    MISSING_IMPORTS.append("Web scraping libraries")

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    MISSING_IMPORTS.append("Twilio")

# Custom CSS for dark theme
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
    .source-card {
        background: #374151;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
        color: white;
    }
    .error-card {
        background: #ef4444;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

class SimpleDatabase:
    """Simple SQLite database handler for demo purposes"""
    
    def __init__(self, db_path="blog_monitor.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
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
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_enabled INTEGER DEFAULT 1,
            whatsapp_enabled INTEGER DEFAULT 1,
            email_address TEXT,
            whatsapp_number TEXT,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
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
                ('Detect FYI', 'https://detect.fyi/', None, 'html'),
            ]
            
            cursor.executemany(
                'INSERT INTO blog_sources (name, url, rss_url, scrape_type) VALUES (?, ?, ?, ?)',
                default_sources
            )
        
        conn.commit()
        conn.close()
    
    def execute_query(self, query, params=None, fetch=False):
        """Execute a database query"""
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

# Initialize database
@st.cache_resource
def get_database():
    """Get database instance"""
    return SimpleDatabase()

def show_system_requirements():
    """Show system requirements and missing dependencies"""
    st.markdown('<div class="error-card">', unsafe_allow_html=True)
    st.markdown("## ⚠️ System Requirements")
    
    if MISSING_IMPORTS:
        st.markdown("### Missing Dependencies:")
        for missing in MISSING_IMPORTS:
            st.markdown(f"❌ {missing}")
        
        st.markdown("### To fix this, install the requirements:")
        st.code("pip install -r requirements.txt")
        
        st.markdown("### Environment Variables Needed:")
        env_vars = [
            "OPENAI_API_KEY - For AI article summarization",
            "EMAIL_ADDRESS - For email notifications", 
            "EMAIL_PASSWORD - For email notifications",
            "TWILIO_ACCOUNT_SID - For WhatsApp notifications",
            "TWILIO_AUTH_TOKEN - For WhatsApp notifications",
            "TWILIO_PHONE_NUMBER - For WhatsApp notifications"
        ]
        
        for var in env_vars:
            status = "✅" if var.split(" -")[0] in os.environ else "❌"
            st.markdown(f"{status} {var}")
    
    st.markdown('</div>', unsafe_allow_html=True)

def main():
    """Main Streamlit application"""
    # Sidebar navigation
    st.sidebar.title("🔒 Blog Monitor")
    
    if MISSING_IMPORTS:
        st.sidebar.error(f"Missing: {', '.join(MISSING_IMPORTS)}")
    
    page = st.sidebar.selectbox(
        "Navigation",
        ["System Status", "Dashboard", "Articles", "Settings", "Sources"]
    )
    
    if page == "System Status":
        show_system_status()
    elif page == "Dashboard":
        show_dashboard()
    elif page == "Articles":
        show_articles()
    elif page == "Settings":
        show_settings()
    elif page == "Sources":
        show_sources()

def show_system_status():
    """Display system status and requirements"""
    st.markdown('<div class="main-header"><h1>🔧 System Status</h1></div>', unsafe_allow_html=True)
    
    # Show missing imports if any
    if MISSING_IMPORTS:
        show_system_requirements()
        return
    
    # System checks
    st.subheader("🔍 System Checks")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Dependencies")
        deps = [
            ("Flask/SQLAlchemy", FLASK_AVAILABLE),
            ("OpenAI", OPENAI_AVAILABLE),
            ("Web Scraping", SCRAPING_AVAILABLE),
            ("Twilio", TWILIO_AVAILABLE)
        ]
        
        for name, available in deps:
            status = "✅" if available else "❌"
            st.markdown(f"{status} {name}")
    
    with col2:
        st.markdown("### Environment Variables")
        env_vars = [
            "OPENAI_API_KEY",
            "EMAIL_ADDRESS",
            "EMAIL_PASSWORD",
            "TWILIO_ACCOUNT_SID"
        ]
        
        for var in env_vars:
            status = "✅" if os.environ.get(var) else "❌"
            st.markdown(f"{status} {var}")
    
    # Manual controls
    if FLASK_AVAILABLE and SCRAPING_AVAILABLE:
        st.subheader("🎮 Manual Controls")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Test Scraping"):
                st.info("Scraping functionality available")
        
        with col2:
            if st.button("🤖 Test AI Processing"):
                if OPENAI_AVAILABLE and os.environ.get("OPENAI_API_KEY"):
                    st.success("OpenAI configuration ready")
                else:
                    st.error("OpenAI not configured")
        
        with col3:
            if st.button("📧 Test Notifications"):
                if os.environ.get("EMAIL_ADDRESS"):
                    st.success("Email configuration ready")
                else:
                    st.error("Email not configured")

def show_dashboard():
    """Display dashboard with statistics"""
    st.markdown('<div class="main-header"><h1>🔒 Cybersecurity Blog Monitor</h1><p>Real-time monitoring of cybersecurity blogs with AI-powered summaries</p></div>', unsafe_allow_html=True)
    
    if MISSING_IMPORTS:
        st.error("⚠️ Missing dependencies. Please check System Status.")
        return
    
    db = get_database()
    
    # Get statistics
    total_articles = db.execute_query("SELECT COUNT(*) FROM articles", fetch=True)[0][0]
    processed_articles = db.execute_query("SELECT COUNT(*) FROM articles WHERE processed = 1", fetch=True)[0][0]
    
    # Recent articles count (last 7 days)
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    recent_articles = db.execute_query(
        "SELECT COUNT(*) FROM articles WHERE scraped_date >= ?", 
        (week_ago,), 
        fetch=True
    )[0][0]
    
    active_sources = db.execute_query("SELECT COUNT(*) FROM blog_sources WHERE active = 1", fetch=True)[0][0]
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Total Articles", total_articles)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col2:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Processed Articles", processed_articles)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col3:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Recent Articles (7 days)", recent_articles)
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col4:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.metric("Active Sources", active_sources)
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Recent articles
    st.subheader("Recent Articles")
    recent_articles_data = db.execute_query(
        "SELECT title, source, url, summary, published_date FROM articles ORDER BY scraped_date DESC LIMIT 5",
        fetch=True
    )
    
    for article in recent_articles_data:
        title, source, url, summary, published_date = article
        
        st.markdown('<div class="article-card">', unsafe_allow_html=True)
        st.markdown(f"**{title}**")
        st.markdown(f"*Source: {source}* | *Published: {published_date or 'Unknown'}*")
        
        if summary:
            st.markdown(f"**Summary:** {summary[:200]}...")
        
        st.markdown(f"[Read Full Article]({url})")
        st.markdown('</div>', unsafe_allow_html=True)

def show_articles():
    """Display articles with filtering"""
    st.header("📰 Articles")
    
    if MISSING_IMPORTS:
        st.error("⚠️ Missing dependencies. Please check System Status.")
        return
    
    db = get_database()
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        sources_data = db.execute_query("SELECT DISTINCT source FROM articles", fetch=True)
        sources = ["All"] + [row[0] for row in sources_data]
        selected_source = st.selectbox("Filter by Source", sources)
    
    with col2:
        processed_filter = st.selectbox("Processing Status", ["All", "Processed", "Unprocessed"])
    
    with col3:
        search_term = st.text_input("Search articles")
    
    # Build query
    query = "SELECT title, source, url, summary, key_points, processed, notification_sent, published_date FROM articles WHERE 1=1"
    params = []
    
    if selected_source != "All":
        query += " AND source = ?"
        params.append(selected_source)
    
    if processed_filter == "Processed":
        query += " AND processed = 1"
    elif processed_filter == "Unprocessed":
        query += " AND processed = 0"
    
    if search_term:
        query += " AND title LIKE ?"
        params.append(f"%{search_term}%")
    
    query += " ORDER BY scraped_date DESC LIMIT 20"
    
    articles = db.execute_query(query, params, fetch=True)
    
    # Display articles
    for article in articles:
        title, source, url, summary, key_points, processed, notification_sent, published_date = article
        
        with st.expander(f"{title} ({source})"):
            st.markdown(f"**Published:** {published_date or 'Unknown'}")
            st.markdown(f"**URL:** [Link]({url})")
            
            if summary:
                st.markdown("**Summary:**")
                st.markdown(summary)
            
            if key_points:
                st.markdown("**Key Points:**")
                st.markdown(key_points)
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Processed:** {'✅' if processed else '❌'}")
            with col2:
                st.markdown(f"**Notified:** {'✅' if notification_sent else '❌'}")

def show_settings():
    """Display notification settings"""
    st.header("⚙️ Notification Settings")
    
    if MISSING_IMPORTS:
        st.error("⚠️ Missing dependencies. Please check System Status.")
        return
    
    db = get_database()
    
    # Get current settings
    settings_data = db.execute_query(
        "SELECT email_enabled, email_address, whatsapp_enabled, whatsapp_number FROM notification_settings LIMIT 1",
        fetch=True
    )
    
    if settings_data:
        email_enabled, email_address, whatsapp_enabled, whatsapp_number = settings_data[0]
    else:
        email_enabled, email_address, whatsapp_enabled, whatsapp_number = 1, "", 1, ""
    
    # Email settings
    st.subheader("📧 Email Settings")
    new_email_enabled = st.checkbox("Enable Email Notifications", value=bool(email_enabled))
    new_email_address = st.text_input("Email Address", value=email_address or "")
    
    # WhatsApp settings
    st.subheader("📱 WhatsApp Settings")
    new_whatsapp_enabled = st.checkbox("Enable WhatsApp Notifications", value=bool(whatsapp_enabled))
    new_whatsapp_number = st.text_input("WhatsApp Number (with country code)", value=whatsapp_number or "")
    
    # Save settings
    if st.button("Save Settings"):
        # Delete existing settings and insert new ones
        db.execute_query("DELETE FROM notification_settings")
        db.execute_query(
            "INSERT INTO notification_settings (email_enabled, email_address, whatsapp_enabled, whatsapp_number) VALUES (?, ?, ?, ?)",
            (int(new_email_enabled), new_email_address, int(new_whatsapp_enabled), new_whatsapp_number)
        )
        st.success("Settings saved successfully!")
        st.rerun()

def show_sources():
    """Display and manage blog sources"""
    st.header("📚 Blog Sources")
    
    if MISSING_IMPORTS:
        st.error("⚠️ Missing dependencies. Please check System Status.")
        return
    
    db = get_database()
    
    # Add new source
    with st.expander("Add New Source"):
        st.subheader("Add Blog Source")
        
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
        "SELECT id, name, url, scrape_type, active, last_scraped FROM blog_sources",
        fetch=True
    )
    
    for source in sources:
        source_id, name, url, scrape_type, active, last_scraped = source
        
        st.markdown('<div class="source-card">', unsafe_allow_html=True)
        
        col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
        
        with col1:
            st.markdown(f"**{name}**")
            st.markdown(f"[{url}]({url})")
        
        with col2:
            st.markdown(f"**Type:** {scrape_type}")
            st.markdown(f"**Last Scraped:** {last_scraped or 'Never'}")
        
        with col3:
            status = "✅ Active" if active else "❌ Inactive"
            st.markdown(f"**Status:** {status}")
        
        with col4:
            if st.button("Toggle", key=f"toggle_{source_id}"):
                db.execute_query(
                    "UPDATE blog_sources SET active = ? WHERE id = ?",
                    (1 - active, source_id)
                )
                st.rerun()
            
            if st.button("Delete", key=f"delete_{source_id}"):
                db.execute_query("DELETE FROM blog_sources WHERE id = ?", (source_id,))
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
