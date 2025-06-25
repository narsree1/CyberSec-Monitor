# Cybersecurity Blog Monitor

A comprehensive monitoring system for cybersecurity blogs with AI-powered summarization and intelligent notifications.

## Features

🔒 **Blog Source Management** - Add, edit, and delete cybersecurity blog sources  
🤖 **AI-Powered Summarization** - Automatic article summarization using OpenAI  
📧 **Smart Notifications** - Email and WhatsApp alerts for new content  
📊 **Analytics Dashboard** - Real-time statistics and monitoring  
⚡ **Manual Controls** - On-demand scraping and notification triggers  
🖥️ **System Health** - Built-in status monitoring and diagnostics  

## Quick Start

### Local Development
```bash
streamlit run streamlit_app.py
```

### Cloud Deployment

**1. Repository Setup**
- Push code to GitHub repository
- Ensure all files are committed, especially `streamlit_app.py` and `.streamlit/config.toml`

**2. Streamlit Cloud Configuration**
- Navigate to [share.streamlit.io](https://share.streamlit.io)
- Connect your GitHub account
- Select your repository
- Set main file path: `streamlit_app.py`
- Click "Deploy"

**3. Environment Configuration**

Add these secrets in Streamlit Cloud's secrets management:

```toml
# Database
DATABASE_URL = "your_postgresql_url"

# OpenAI
OPENAI_API_KEY = "your_openai_key"

# Email Configuration
EMAIL_ADDRESS = "your_email@gmail.com"
EMAIL_PASSWORD = "your_app_password"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = "587"

# Twilio (WhatsApp)
TWILIO_ACCOUNT_SID = "your_twilio_sid"
TWILIO_AUTH_TOKEN = "your_twilio_token"
TWILIO_PHONE_NUMBER = "your_twilio_number"

# Session Security
SESSION_SECRET = "your_random_secret_key"
```

**4. Database Setup**
- Use a cloud PostgreSQL service (Supabase, Neon, Railway, or ElephantSQL)
- Tables are automatically created on first application run
- Update `DATABASE_URL` with your cloud database connection string

## Architecture

**Frontend**: Streamlit native components with responsive design  
**Backend**: SQLAlchemy models with PostgreSQL database  
**AI Integration**: OpenAI API for content summarization  
**Notifications**: Email (SMTP) and WhatsApp (Twilio) support  
**Styling**: Custom dark theme optimized for cybersecurity monitoring  

## File Structure

```
├── streamlit_app.py          # Main application entry point
├── .streamlit/
│   └── config.toml          # Streamlit configuration
├── models.py                # Database models and schemas
├── scraper.py              # Web scraping and content extraction
├── ai_service.py           # OpenAI integration and summarization
├── notification_service.py # Email and WhatsApp notifications
├── scheduler.py            # Background task scheduling
└── app.py                  # Database context management
```

## Core Capabilities

**Real-time Monitoring**: Automatic content refresh and live updates  
**Interactive Interface**: Native Streamlit widgets and controls  
**Mobile Responsive**: Optimized for desktop and mobile viewing  
**Dark Theme**: Professional cybersecurity-focused design  
**Health Checks**: Built-in system diagnostics and API testing  

## Troubleshooting

**Database Issues**
- Verify `DATABASE_URL` is correctly configured in secrets
- Check database connection permissions and network access

**API Configuration**
- Ensure all API keys are valid and properly set
- Test connections using built-in diagnostic tools

**Scheduler Problems**
- Background tasks may require manual restart after deployment
- Monitor system status page for scheduler health

**Debugging Resources**
- Check Streamlit Cloud deployment logs
- Use "System Status" page for application health monitoring
- Test individual components with built-in test buttons

## Getting Support

For deployment issues, check Streamlit Cloud documentation. For application-specific problems, review the system status dashboard and error logs for detailed diagnostics.
