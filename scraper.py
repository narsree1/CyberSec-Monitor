import requests
import feedparser
import trafilatura
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta
import logging
from app import db
from models import Article, ScrapingLog
import time

logger = logging.getLogger(__name__)

def initialize_default_sources():
    """Initialize default blog sources if none exist"""
    from app import db
    from models import BlogSource
    
    # Check if any sources exist
    if BlogSource.query.count() > 0:
        return
    
    logger.info("Initializing default blog sources...")
    
    default_sources = [
        {
            'name': 'Detection Engineering',
            'url': 'https://www.detectionengineering.net/',
            'scrape_type': 'html'
        },
        {
            'name': 'Rohit Tamma Substack',
            'url': 'https://rohittamma.substack.com/',
            'rss_url': 'https://rohittamma.substack.com/feed',
            'scrape_type': 'rss'
        },
        {
            'name': 'Cybersec Automation',
            'url': 'https://www.cybersec-automation.com/',
            'scrape_type': 'html'
        },
        {
            'name': 'Anton on Security',
            'url': 'https://medium.com/@anton.on.security',
            'rss_url': 'https://medium.com/feed/@anton.on.security',
            'scrape_type': 'rss'
        },
        {
            'name': 'Google Cloud Security Blog',
            'url': 'https://www.googlecloudcommunity.com/gc/Community-Blog/bg-p/security-blog',
            'scrape_type': 'html'
        },
        {
            'name': 'Detect FYI',
            'url': 'https://detect.fyi/',
            'scrape_type': 'html'
        },
        {
            'name': 'Dylan H Williams Medium',
            'url': 'https://medium.com/@dylanhwilliams',
            'rss_url': 'https://medium.com/feed/@dylanhwilliams',
            'scrape_type': 'rss'
        }
    ]
    
    for source_data in default_sources:
        source = BlogSource(
            name=source_data['name'],
            url=source_data['url'],
            rss_url=source_data.get('rss_url'),
            scrape_type=source_data['scrape_type']
        )
        db.session.add(source)
    
    db.session.commit()
    logger.info(f"Added {len(default_sources)} default blog sources")

def get_website_text_content(url):
    """Extract clean text content from a website using trafilatura"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            return text
        return None
    except Exception as e:
        logger.error(f"Error extracting content from {url}: {e}")
        return None

def scrape_rss_feed(blog_config):
    """Scrape articles from RSS feed"""
    articles = []
    try:
        feed = feedparser.parse(blog_config['rss_feed'])
        logger.info(f"Parsing RSS feed for {blog_config['name']}: {len(feed.entries)} entries found")
        
        for entry in feed.entries[:5]:  # Limit to recent 5 articles
            # Check if article already exists
            existing = Article.query.filter_by(url=entry.link).first()
            if existing:
                continue
            
            # Parse published date
            published_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_date = datetime(*entry.published_parsed[:6])
            
            # Extract content
            content = get_website_text_content(entry.link)
            
            article_data = {
                'title': entry.title,
                'url': entry.link,
                'source': blog_config['name'],
                'content': content,
                'published_date': published_date
            }
            articles.append(article_data)
            
    except Exception as e:
        logger.error(f"Error scraping RSS feed for {blog_config['name']}: {e}")
        
    return articles

def scrape_website_links(blog_config):
    """Scrape article links directly from website"""
    articles = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(blog_config['url'], headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find article links based on common patterns
        article_links = set()
        
        # Common selectors for article links
        selectors = [
            'a[href*="/blog/"]',
            'a[href*="/post/"]',
            'a[href*="/article/"]',
            'h2 a', 'h3 a',
            '.post-title a',
            '.article-title a',
            '.entry-title a'
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            for link in links[:10]:  # Limit to avoid too many requests
                href = link.get('href')
                if href:
                    full_url = urljoin(blog_config['url'], href)
                    if full_url.startswith('http'):
                        article_links.add(full_url)
        
        logger.info(f"Found {len(article_links)} potential articles for {blog_config['name']}")
        
        # Process each article link
        for url in list(article_links)[:5]:  # Limit to 5 recent articles
            try:
                # Check if article already exists
                existing = Article.query.filter_by(url=url).first()
                if existing:
                    continue
                
                # Get article content
                content = get_website_text_content(url)
                if not content or len(content.strip()) < 100:
                    continue
                
                # Extract title from content or URL
                title = extract_title_from_content(content) or url.split('/')[-1].replace('-', ' ').title()
                
                article_data = {
                    'title': title,
                    'url': url,
                    'source': blog_config['name'],
                    'content': content,
                    'published_date': None  # Will be estimated later
                }
                articles.append(article_data)
                
                # Rate limiting
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing article {url}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error scraping website {blog_config['name']}: {e}")
        
    return articles

def extract_title_from_content(content):
    """Extract title from article content"""
    if not content:
        return None
    
    lines = content.strip().split('\n')
    for line in lines[:5]:  # Check first few lines
        line = line.strip()
        if len(line) > 10 and len(line) < 200:  # Reasonable title length
            return line
    return None

def scrape_blog(blog_config):
    """Scrape a single blog for new articles"""
    logger.info(f"Scraping {blog_config['name']}...")
    
    articles = []
    error_message = None
    
    try:
        if blog_config.get('rss_feed'):
            articles = scrape_rss_feed(blog_config)
        else:
            articles = scrape_website_links(blog_config)
            
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error scraping {blog_config['name']}: {e}")
    
    # Save articles to database
    saved_count = 0
    for article_data in articles:
        try:
            article = Article(**article_data)
            db.session.add(article)
            db.session.commit()
            saved_count += 1
            logger.info(f"Saved article: {article_data['title']}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error saving article: {e}")
    
    # Log scraping result
    status = 'error' if error_message else ('success' if saved_count > 0 else 'no_new_articles')
    log_entry = ScrapingLog(
        source=blog_config['name'],
        status=status,
        message=error_message or f"Found {saved_count} new articles",
        articles_found=saved_count
    )
    
    try:
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving scraping log: {e}")
    
    return saved_count

def scrape_all_sources():
    """Scrape all configured blog sources from database"""
    from app import db
    from models import BlogSource
    from datetime import datetime
    
    logger.info("Starting scraping of all sources...")
    
    # Initialize default sources if none exist
    initialize_default_sources()
    
    # Get active blog sources from database
    blog_sources = BlogSource.query.filter_by(active=True).all()
    
    if not blog_sources:
        logger.warning("No active blog sources found in database")
        return 0
    
    total_articles = 0
    
    for source in blog_sources:
        try:
            blog_config = {
                'name': source.name,
                'url': source.url,
                'type': source.scrape_type,
                'rss_feed': source.rss_url
            }
            
            count = scrape_blog(blog_config)
            total_articles += count
            
            # Update last_scraped timestamp
            source.last_scraped = datetime.utcnow()
            db.session.commit()
            
            # Rate limiting between sources
            time.sleep(2)
            
        except Exception as e:
            logger.error(f"Error scraping {source.name}: {e}")
    
    logger.info(f"Scraping completed. Total new articles: {total_articles}")
    
    # Process new articles for summarization
    if total_articles > 0:
        from ai_service import process_new_articles
        process_new_articles()
    
    return total_articles
