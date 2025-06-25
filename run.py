#!/usr/bin/env python3
"""
Startup script for the Cybersecurity Blog Monitor
"""

import os
import sys
import subprocess
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = [
        'streamlit',
        'flask',
        'flask-sqlalchemy', 
        'openai',
        'requests',
        'beautifulsoup4',
        'feedparser',
        'trafilatura',
        'twilio',
        'apscheduler',
        'pandas'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    return missing_packages

def install_dependencies():
    """Install missing dependencies"""
    logger.info("Installing dependencies from requirements.txt...")
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'])
        logger.info("Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install dependencies: {e}")
        return False

def create_env_template():
    """Create a template .env file if it doesn't exist"""
    env_template = """# Cybersecurity Blog Monitor Environment Variables

# OpenAI Configuration (Required for AI summarization)
OPENAI_API_KEY=your_openai_api_key_here

# Email Configuration (Optional - for email notifications)
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=your_app_password_here
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# Twilio Configuration (Optional - for WhatsApp notifications)
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890

# Database Configuration (Optional - defaults to SQLite)
DATABASE_URL=sqlite:///blog_monitor.db

# Session Secret (Optional - for web sessions)
SESSION_SECRET=your_secret_key_here
"""
    
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write(env_template)
        logger.info("Created .env template file. Please configure your API keys.")

def run_streamlit():
    """Run the Streamlit application"""
    logger.info("Starting Streamlit application...")
    try:
        # Use the fixed streamlit app
        subprocess.run([
            sys.executable, '-m', 'streamlit', 'run', 
            'streamlit_app_fixed.py',
            '--server.port=8501',
            '--server.address=0.0.0.0'
        ])
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Error running Streamlit: {e}")

def main():
    """Main startup function"""
    logger.info("=== Cybersecurity Blog Monitor Startup ===")
    
    # Create environment template
    create_env_template()
    
    # Check dependencies
    missing = check_dependencies()
    if missing:
        logger.warning(f"Missing packages: {missing}")
        if os.path.exists('requirements.txt'):
            install_dependencies()
        else:
            logger.error("requirements.txt not found. Please install dependencies manually.")
            return
    
    # Check again after installation
    missing_after = check_dependencies()
    if missing_after:
        logger.warning(f"Some packages still missing: {missing_after}")
        logger.info("The application will run with limited functionality.")
    
    # Run the application
    run_streamlit()

if __name__ == "__main__":
    main()
