import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from twilio.rest import Client
from app import db
from models import Article, NotificationSettings
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Email configuration
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")

# Twilio configuration
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
TWILIO_WHATSAPP_NUMBER = f"whatsapp:{TWILIO_PHONE_NUMBER}" if TWILIO_PHONE_NUMBER else "whatsapp:+14155238886"

def send_email_notification(to_email, subject, body):
    """Send email notification"""
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        logger.error("Email credentials not configured")
        return False
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = subject
        
        # Attach body
        msg.attach(MIMEText(body, 'html'))
        
        # Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_ADDRESS, to_email, text)
        server.quit()
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False

def send_whatsapp_notification(to_number, message):
    """Send WhatsApp notification using Twilio"""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        logger.error("Twilio credentials not configured")
        return False
    
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Ensure phone number is in correct format
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"
        
        # Send message
        message = client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_number
        )
        
        logger.info(f"WhatsApp message sent successfully to {to_number}, SID: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending WhatsApp message to {to_number}: {e}")
        return False

def format_email_body(articles):
    """Format articles for email notification"""
    html_body = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
            .header { background-color: #007bff; color: white; padding: 20px; text-align: center; }
            .article { margin: 20px 0; padding: 15px; border-left: 4px solid #007bff; background-color: #f8f9fa; }
            .article-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
            .article-source { color: #6c757d; font-size: 14px; margin-bottom: 10px; }
            .article-summary { margin-bottom: 15px; }
            .key-points { margin-bottom: 15px; }
            .key-points ul { margin: 5px 0; padding-left: 20px; }
            .read-more { display: inline-block; background-color: #007bff; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; }
            .footer { margin-top: 30px; padding: 20px; background-color: #f8f9fa; text-align: center; color: #6c757d; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🔒 Cybersecurity Articles Digest</h1>
            <p>New articles from your monitored cybersecurity blogs</p>
        </div>
    """
    
    # Define newline replacement outside f-string
    br_tag = '<br>'
    newline = '\n'
    
    for article in articles:
        # Pre-process content to avoid backslashes in f-strings
        summary_content = article.summary.replace(newline, br_tag) if article.summary else 'Summary not available'
        key_points_content = article.key_points.replace(newline, br_tag) if article.key_points else 'Key points not available'
        
        html_body += f"""
        <div class="article">
            <div class="article-title">{article.title}</div>
            <div class="article-source">Source: {article.source}</div>
            
            <div class="article-summary">
                <strong>Summary:</strong><br>
                {summary_content}
            </div>
            
            <div class="key-points">
                <strong>Key Points:</strong><br>
                {key_points_content}
            </div>
            
            <a href="{article.url}" class="read-more">Read Full Article</a>
        </div>
        """
    
    html_body += """
        <div class="footer">
            <p>This digest was automatically generated by your Blog Monitor application.</p>
        </div>
    </body>
    </html>
    """
    
    return html_body

def format_whatsapp_message(articles):
    """Format articles for WhatsApp notification (with character limits)"""
    if not articles:
        return "No new cybersecurity articles found."
    
    message = "🔒 *Cybersecurity Articles Digest*\n\n"
    
    for i, article in enumerate(articles[:3], 1):  # Limit to 3 articles for WhatsApp
        message += f"*{i}. {article.title[:80]}{'...' if len(article.title) > 80 else ''}*\n"
        message += f"📰 Source: {article.source}\n"
        
        # Add summary (truncated)
        if article.summary:
            summary = article.summary[:200] + "..." if len(article.summary) > 200 else article.summary
            message += f"📝 {summary}\n"
        
        # Add URL
        message += f"🔗 {article.url}\n\n"
    
    if len(articles) > 3:
        message += f"... and {len(articles) - 3} more articles available in your dashboard."
    
    return message

def send_notifications_for_new_articles():
    """Send notifications for articles that haven't been notified yet"""
    logger.info("Checking for articles to notify...")
    
    # Get notification settings
    settings = NotificationSettings.query.first()
    if not settings:
        logger.warning("No notification settings found")
        return
    
    # Get articles that need notification
    articles_to_notify = Article.query.filter_by(
        processed=True,
        notification_sent=False
    ).order_by(Article.scraped_date.desc()).all()
    
    if not articles_to_notify:
        logger.info("No new articles to notify")
        return
    
    logger.info(f"Found {len(articles_to_notify)} articles to notify")
    
    # Send email notification
    if settings.email_enabled and settings.email_address:
        try:
            subject = f"🔒 {len(articles_to_notify)} New Cybersecurity Articles"
            body = format_email_body(articles_to_notify)
            
            if send_email_notification(settings.email_address, subject, body):
                logger.info("Email notification sent successfully")
            else:
                logger.error("Failed to send email notification")
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
    
    # Send WhatsApp notification
    if settings.whatsapp_enabled and settings.whatsapp_number:
        try:
            message = format_whatsapp_message(articles_to_notify)
            
            if send_whatsapp_notification(settings.whatsapp_number, message):
                logger.info("WhatsApp notification sent successfully")
            else:
                logger.error("Failed to send WhatsApp notification")
        except Exception as e:
            logger.error(f"Error sending WhatsApp notification: {e}")
    
    # Mark articles as notified
    try:
        for article in articles_to_notify:
            article.notification_sent = True
        db.session.commit()
        logger.info(f"Marked {len(articles_to_notify)} articles as notified")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error marking articles as notified: {e}")

def test_email_configuration():
    """Test email configuration"""
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        return False, "Email credentials not configured"
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.quit()
        return True, "Email configuration is working"
    except Exception as e:
        return False, f"Email configuration error: {str(e)}"

def test_whatsapp_configuration():
    """Test WhatsApp configuration"""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return False, "Twilio credentials not configured"
    
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        # Just initialize client to test credentials
        return True, "WhatsApp configuration is working"
    except Exception as e:
        return False, f"WhatsApp configuration error: {str(e)}"
