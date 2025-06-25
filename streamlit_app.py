import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import sys

# Add current directory to path for imports
sys.path.append('.')

# Set environment variables from Streamlit secrets if available
if hasattr(st, 'secrets'):
    for key, value in st.secrets.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                os.environ[sub_key] = str(sub_value)
        else:
            os.environ[key] = str(value)

# Import existing modules
try:
    from models import Article, NotificationSettings, BlogSource, ScrapingLog
    from app import db, app
    from scraper import scrape_all_sources, initialize_default_sources
    from ai_service import process_new_articles, test_openai_connection
    from notification_service import send_notifications_for_new_articles, test_email_configuration, test_whatsapp_configuration
    from scheduler import start_scheduler, get_scheduler_status
except ImportError as e:
    st.error(f"Import error: {e}")
    st.stop()

# Configure Streamlit page
st.set_page_config(
    page_title="Cybersecurity Blog Monitor",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database and scheduler within app context
@st.cache_resource
def initialize_app():
    """Initialize the application and start scheduler"""
    with app.app_context():
        db.create_all()
        initialize_default_sources()
        start_scheduler()
    return True

# Custom CSS for dark theme
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1f2937 0%, #374151 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #374151;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #3b82f6;
    }
    .article-card {
        background: #1f2937;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        border-left: 4px solid #10b981;
    }
    .source-card {
        background: #374151;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

def main():
    """Main Streamlit application"""
    initialize_app()
    
    # Sidebar navigation
    st.sidebar.title("🔒 Blog Monitor")
    page = st.sidebar.selectbox(
        "Navigation",
        ["Dashboard", "Articles", "Settings", "Sources", "System Status"]
    )
    
    if page == "Dashboard":
        show_dashboard()
    elif page == "Articles":
        show_articles()
    elif page == "Settings":
        show_settings()
    elif page == "Sources":
        show_sources()
    elif page == "System Status":
        show_system_status()

def show_dashboard():
    """Display dashboard with statistics and recent articles"""
    st.markdown('<div class="main-header"><h1>🔒 Cybersecurity Blog Monitor</h1><p>Real-time monitoring of cybersecurity blogs with AI-powered summaries</p></div>', unsafe_allow_html=True)
    
    with app.app_context():
        # Statistics
        total_articles = Article.query.count()
        processed_articles = Article.query.filter_by(processed=True).count()
        recent_articles = Article.query.filter(
            Article.scraped_date >= datetime.utcnow() - timedelta(days=7)
        ).count()
        active_sources = BlogSource.query.filter_by(active=True).count()
        
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
        recent_articles_query = Article.query.order_by(Article.scraped_date.desc()).limit(5).all()
        
        for article in recent_articles_query:
            st.markdown('<div class="article-card">', unsafe_allow_html=True)
            st.markdown(f"**{article.title}**")
            st.markdown(f"*Source: {article.source}* | *Published: {article.published_date or 'Unknown'}*")
            
            if article.summary:
                st.markdown(f"**Summary:** {article.summary[:200]}...")
            
            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button(f"Read Full Article", key=f"read_{article.id}"):
                    st.markdown(f"[Open Article]({article.url})")
            
            st.markdown('</div>', unsafe_allow_html=True)

def show_articles():
    """Display articles with filtering and search"""
    st.header("📰 Articles")
    
    with app.app_context():
        # Filters
        col1, col2, col3 = st.columns(3)
        
        with col1:
            sources = [source.name for source in BlogSource.query.all()]
            selected_source = st.selectbox("Filter by Source", ["All"] + sources)
        
        with col2:
            processed_filter = st.selectbox("Processing Status", ["All", "Processed", "Unprocessed"])
        
        with col3:
            search_term = st.text_input("Search articles")
        
        # Query articles
        query = Article.query
        
        if selected_source != "All":
            query = query.filter(Article.source == selected_source)
        
        if processed_filter == "Processed":
            query = query.filter(Article.processed == True)
        elif processed_filter == "Unprocessed":
            query = query.filter(Article.processed == False)
        
        if search_term:
            query = query.filter(Article.title.contains(search_term))
        
        articles = query.order_by(Article.scraped_date.desc()).limit(20).all()
        
        # Display articles
        for article in articles:
            with st.expander(f"{article.title} ({article.source})"):
                st.markdown(f"**Published:** {article.published_date or 'Unknown'}")
                st.markdown(f"**URL:** [Link]({article.url})")
                
                if article.summary:
                    st.markdown("**Summary:**")
                    st.markdown(article.summary)
                
                if article.key_points:
                    st.markdown("**Key Points:**")
                    st.markdown(article.key_points)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Processed:** {'✅' if article.processed else '❌'}")
                with col2:
                    st.markdown(f"**Notified:** {'✅' if article.notification_sent else '❌'}")

def show_settings():
    """Display and manage notification settings"""
    st.header("⚙️ Notification Settings")
    
    with app.app_context():
        settings = NotificationSettings.query.first()
        if not settings:
            settings = NotificationSettings()
            db.session.add(settings)
            db.session.commit()
        
        # Email settings
        st.subheader("📧 Email Settings")
        email_enabled = st.checkbox("Enable Email Notifications", value=settings.email_enabled)
        email_address = st.text_input("Email Address", value=settings.email_address or "")
        
        # WhatsApp settings
        st.subheader("📱 WhatsApp Settings")
        whatsapp_enabled = st.checkbox("Enable WhatsApp Notifications", value=settings.whatsapp_enabled)
        whatsapp_number = st.text_input("WhatsApp Number (with country code)", value=settings.whatsapp_number or "")
        
        # Save settings
        if st.button("Save Settings"):
            settings.email_enabled = email_enabled
            settings.email_address = email_address
            settings.whatsapp_enabled = whatsapp_enabled
            settings.whatsapp_number = whatsapp_number
            settings.last_updated = datetime.utcnow()
            
            db.session.commit()
            st.success("Settings saved successfully!")
        
        # Test configurations
        st.subheader("🧪 Test Configurations")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("Test Email"):
                success, message = test_email_configuration()
                if success:
                    st.success(message)
                else:
                    st.error(message)
        
        with col2:
            if st.button("Test WhatsApp"):
                success, message = test_whatsapp_configuration()
                if success:
                    st.success(message)
                else:
                    st.error(message)
        
        with col3:
            if st.button("Test OpenAI"):
                success, message = test_openai_connection()
                if success:
                    st.success(message)
                else:
                    st.error(message)

def show_sources():
    """Display and manage blog sources"""
    st.header("📚 Blog Sources")
    
    with app.app_context():
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
                        new_source = BlogSource(
                            name=name,
                            url=url,
                            rss_url=rss_url if rss_url else None,
                            scrape_type=scrape_type
                        )
                        db.session.add(new_source)
                        db.session.commit()
                        st.success(f"Added source: {name}")
                        st.rerun()
                    else:
                        st.error("Please provide both name and URL")
        
        # Display existing sources
        st.subheader("Current Sources")
        sources = BlogSource.query.all()
        
        for source in sources:
            st.markdown('<div class="source-card">', unsafe_allow_html=True)
            
            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
            
            with col1:
                st.markdown(f"**{source.name}**")
                st.markdown(f"[{source.url}]({source.url})")
            
            with col2:
                st.markdown(f"**Type:** {source.scrape_type}")
                st.markdown(f"**Last Scraped:** {source.last_scraped or 'Never'}")
            
            with col3:
                status = "✅ Active" if source.active else "❌ Inactive"
                st.markdown(f"**Status:** {status}")
            
            with col4:
                if st.button("Toggle", key=f"toggle_{source.id}"):
                    source.active = not source.active
                    db.session.commit()
                    st.rerun()
                
                if st.button("Delete", key=f"delete_{source.id}"):
                    db.session.delete(source)
                    db.session.commit()
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)

def show_system_status():
    """Display system status and manual controls"""
    st.header("🔧 System Status")
    
    with app.app_context():
        # Scheduler status
        st.subheader("⏰ Scheduler Status")
        scheduler_status = get_scheduler_status()
        if scheduler_status['running']:
            st.success("✅ Scheduler is running")
            st.markdown(f"**Next scraping job:** {scheduler_status.get('next_run', 'Unknown')}")
        else:
            st.error("❌ Scheduler is not running")
        
        # Manual controls
        st.subheader("🎮 Manual Controls")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Trigger Scraping"):
                with st.spinner("Scraping in progress..."):
                    scrape_all_sources()
                st.success("Scraping completed!")
                st.rerun()
        
        with col2:
            if st.button("🤖 Process Articles"):
                with st.spinner("Processing articles with AI..."):
                    process_new_articles()
                st.success("Article processing completed!")
                st.rerun()
        
        with col3:
            if st.button("📧 Send Notifications"):
                with st.spinner("Sending notifications..."):
                    send_notifications_for_new_articles()
                st.success("Notifications sent!")
        
        # Recent logs
        st.subheader("📊 Recent Activity")
        logs = ScrapingLog.query.order_by(ScrapingLog.timestamp.desc()).limit(10).all()
        
        if logs:
            log_data = []
            for log in logs:
                log_data.append({
                    "Timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "Source": log.source,
                    "Status": log.status,
                    "Articles Found": log.articles_found,
                    "Message": log.message[:50] + "..." if log.message and len(log.message) > 50 else log.message
                })
            
            df = pd.DataFrame(log_data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No activity logs found")

if __name__ == "__main__":
    main()
