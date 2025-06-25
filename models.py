from app import db
from datetime import datetime
from sqlalchemy import Text, Boolean, DateTime

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(1000), unique=True, nullable=False)
    source = db.Column(db.String(200), nullable=False)
    content = db.Column(Text)
    summary = db.Column(Text)
    key_points = db.Column(Text)
    published_date = db.Column(DateTime)
    scraped_date = db.Column(DateTime, default=datetime.utcnow)
    processed = db.Column(Boolean, default=False)
    notification_sent = db.Column(Boolean, default=False)
    
    def __repr__(self):
        return f'<Article {self.title}>'

class NotificationSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email_enabled = db.Column(Boolean, default=True)
    whatsapp_enabled = db.Column(Boolean, default=True)
    email_address = db.Column(db.String(200))
    whatsapp_number = db.Column(db.String(20))
    last_updated = db.Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<NotificationSettings {self.email_address}>'

class BlogSource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(1000), nullable=False)
    rss_url = db.Column(db.String(1000))  # Optional RSS feed URL
    scrape_type = db.Column(db.String(50), default='rss')  # 'rss' or 'html'
    active = db.Column(Boolean, default=True)
    created_date = db.Column(DateTime, default=datetime.utcnow)
    last_scraped = db.Column(DateTime)
    
    def __repr__(self):
        return f'<BlogSource {self.name}>'

class ScrapingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), nullable=False)  # success, error, no_new_articles
    message = db.Column(Text)
    articles_found = db.Column(db.Integer, default=0)
    timestamp = db.Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ScrapingLog {self.source} - {self.status}>'
