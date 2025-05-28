#!/bin/bash

# Blogify Automated Setup Script for Ubuntu
# This script automates the entire setup process for the Blogify system

# Exit on any error
set -e

# Check if running as root
if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# Check for required environment variables
if [ -z "$SERPAPI_KEY" ] || [ -z "$GEMINI_KEY" ] || [ -z "$DOMAIN" ]; then
    echo "Error: Required environment variables not set."
    echo "Usage: SERPAPI_KEY=your_key GEMINI_KEY=your_key DOMAIN=yourdomain.com $0"
    exit 1
fi

# Optional environment variables with defaults
REPO_URL=${REPO_URL:-"https://github.com/yourusername/blogify.git"}
SERP_REGION=${SERP_REGION:-"us"}
SERP_CATEGORY=${SERP_CATEGORY:-"all"}
GEMINI_MODEL=${GEMINI_MODEL:-"gemini-1.5-pro"}

# Configuration
APP_DIR=/var/www/blogify
VENV_DIR=$APP_DIR/venv

echo "=== Starting Blogify Automated Setup ==="
echo "Domain: $DOMAIN"
echo "Repository: $REPO_URL"
echo "API regions: $SERP_REGION"
echo "Content category: $SERP_CATEGORY"

# Update system
echo "=== Updating System Packages ==="
apt update
apt upgrade -y

# Install dependencies
echo "=== Installing System Dependencies ==="
apt install -y python3 python3-pip python3-venv nginx redis-server git ufw fail2ban

# Configure firewall
echo "=== Configuring Firewall ==="
ufw allow 'Nginx HTTP'
ufw allow 'Nginx HTTPS'
ufw allow 'OpenSSH'
ufw --force enable

# Create app directory
echo "=== Setting Up Application Directory ==="
mkdir -p $APP_DIR
chown www-data:www-data $APP_DIR

# Clone repository
echo "=== Cloning Code Repository ==="
sudo -u www-data git clone $REPO_URL $APP_DIR

# Setup Python environment
echo "=== Setting Up Python Environment ==="
sudo -u www-data python3 -m venv $VENV_DIR
sudo -u www-data $VENV_DIR/bin/pip install --upgrade pip
sudo -u www-data $VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt

# Create .env file
echo "=== Creating Environment Configuration ==="
sudo -u www-data bash -c "cat > $APP_DIR/.env << EOL
# Django Settings
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
DEBUG=False

# API Keys
SERPAPI_API_KEY=$SERPAPI_KEY
GEMINI_API_KEY=$GEMINI_KEY

# Google Trends Settings
SERP_API_REGION=$SERP_REGION
SERP_API_CATEGORY=$SERP_CATEGORY

# Gemini Model Settings
GEMINI_MODEL=$GEMINI_MODEL

# Celery / Redis Settings
REDIS_URL=redis://localhost:6379/0

# Production Settings
ALLOWED_HOSTS=$DOMAIN,www.$DOMAIN,127.0.0.1,localhost
EOL"

# Run Django migrations
echo "=== Setting Up Database ==="
cd $APP_DIR
sudo -u www-data $VENV_DIR/bin/python manage.py migrate --noinput
sudo -u www-data $VENV_DIR/bin/python manage.py collectstatic --noinput

# Make deployment scripts executable
echo "=== Setting Up Deployment Scripts ==="
chmod +x $APP_DIR/deployment/*.sh

# Configure Gunicorn
echo "=== Configuring Gunicorn ==="
cp $APP_DIR/deployment/gunicorn.service /etc/systemd/system/gunicorn.service
systemctl enable gunicorn
systemctl start gunicorn

# Configure Celery Worker
echo "=== Configuring Celery Worker ==="
cp $APP_DIR/deployment/celery.service /etc/systemd/system/celery.service
systemctl enable celery
systemctl start celery

# Configure Celery Beat
echo "=== Configuring Celery Beat ==="
cp $APP_DIR/deployment/celerybeat.service /etc/systemd/system/celerybeat.service
systemctl enable celerybeat
systemctl start celerybeat

# Configure Nginx
echo "=== Configuring Nginx ==="
cp $APP_DIR/deployment/nginx.conf /etc/nginx/sites-available/blogify
# Replace placeholder domain with actual domain
sed -i "s/yourdomain.com/$DOMAIN/g" /etc/nginx/sites-available/blogify
ln -sf /etc/nginx/sites-available/blogify /etc/nginx/sites-enabled/
# Remove default site if it exists
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

# Setup crontab for maintenance tasks
echo "=== Setting Up Automated Maintenance ==="
(crontab -l 2>/dev/null || echo "") | cat - $APP_DIR/deployment/crontab | crontab -

echo "=== Blogify Setup Completed Successfully! ==="
echo "Your blog site should now be accessible at http://$DOMAIN"
echo ""
echo "To check service status:"
echo "  - systemctl status gunicorn"
echo "  - systemctl status celery"
echo "  - systemctl status celerybeat"
echo "  - systemctl status nginx"
echo ""
echo "The automated blog system is now running and will:"
echo "  - Fetch trending topics hourly"
echo "  - Generate optimized content"
echo "  - Publish blog posts automatically"
echo "  - Backup the database daily"
echo "  - Self-maintain and restart if needed" 