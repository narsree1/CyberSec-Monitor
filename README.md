Cybersecurity Blog Monitor - Streamlit Cloud Deployment
Overview
This application has been converted from Flask to Streamlit for deployment on Streamlit Cloud. The core functionality remains the same: monitoring cybersecurity blogs, AI-powered summarization, and notifications.

Deployment Steps for Streamlit Cloud
1. Repository Setup
Push this code to a GitHub repository
Ensure all files are committed, especially streamlit_app.py and .streamlit/config.toml
2. Streamlit Cloud Configuration
Go to share.streamlit.io
Connect your GitHub account
Select your repository
Set main file path to: streamlit_app.py
Click "Deploy"
3. Environment Variables Setup
In Streamlit Cloud's secrets management, add these variables:

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
4. Database Setup
Use a cloud PostgreSQL service (Supabase, Neon, or Railway)
The app will automatically create tables on first run
Update DATABASE_URL with your cloud database connection string
Key Changes from Flask Version
Architecture
Frontend: Streamlit native components instead of HTML templates
Routing: Streamlit's page-based navigation system
Database: Same SQLAlchemy models, accessed within app context
Styling: Custom CSS with dark theme optimized for Streamlit
Features Maintained
✅ Blog source management (add/edit/delete sources)
✅ Article scraping and AI summarization
✅ Email and WhatsApp notifications
✅ Dashboard with statistics and recent articles
✅ Manual trigger controls
✅ System status monitoring
New Streamlit Features
Real-time Updates: Automatic refresh capabilities
Interactive Components: Native Streamlit widgets
Responsive Design: Mobile-optimized interface
Dark Theme: Custom dark theme for cybersecurity aesthetic
File Structure
├── streamlit_app.py          # Main Streamlit application
├── .streamlit/
│   └── config.toml          # Streamlit configuration
├── models.py                # Database models (unchanged)
├── scraper.py              # Web scraping logic (unchanged)
├── ai_service.py           # OpenAI integration (unchanged)
├── notification_service.py # Email/WhatsApp notifications (unchanged)
├── scheduler.py            # Background scheduling (unchanged)
└── app.py                  # Flask app context (for database)
Running Locally
streamlit run streamlit_app.py
Troubleshooting
Common Issues
Database Connection: Ensure DATABASE_URL is properly set in secrets
API Keys: Verify all API keys are correctly configured
Scheduler: Background scheduler may need manual restart after deployment
Logs and Debugging
Check Streamlit Cloud logs for deployment issues
Use the "System Status" page to monitor application health
Test API connections using the built-in test buttons
Migration Notes
All existing data will be preserved when migrating databases
Configuration settings need to be re-entered in the new interface
Blog sources will be automatically initialized if none exist
