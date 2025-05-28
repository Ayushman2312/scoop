#!/bin/bash

# Exit on any error
set -e

# Configuration
APP_DIR=/var/www/blogify
VENV_DIR=$APP_DIR/venv
REPO_URL=https://github.com/yourusername/blogify.git
DOMAIN=yourdomain.com

# Check if running as root
if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# Update system
echo "Updating system packages..."
apt update
apt upgrade -y

# Install dependencies
echo "Installing system dependencies..."
apt install -y python3 python3-pip python3-venv nginx redis-server supervisor git

# Create app directory
echo "Setting up application directory..."
mkdir -p $APP_DIR
chown www-data:www-data $APP_DIR

# Switch to www-data user for repository operations
sudo -u www-data bash << EOF
# Clone or update repository
if [ -d "$APP_DIR/.git" ]; then
    echo "Updating existing repository..."
    cd $APP_DIR
    git pull
else
    echo "Cloning repository..."
    git clone $REPO_URL $APP_DIR
fi

# Setup Python environment
echo "Setting up Python virtual environment..."
python3 -m venv $VENV_DIR
$VENV_DIR/bin/pip install --upgrade pip
$VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt

# Create .env file if it doesn't exist
if [ ! -f "$APP_DIR/.env" ]; then
    echo "Creating .env file..."
    cat > $APP_DIR/.env << EOL
# Django Settings
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
DEBUG=False

# API Keys
SERPAPI_API_KEY=${SERPAPI_KEY}
GEMINI_API_KEY=${GEMINI_KEY}

# Google Trends Settings
SERP_API_REGION=${SERP_REGION:-us}
SERP_API_CATEGORY=${SERP_CATEGORY:-all}

# Gemini Model Settings
GEMINI_MODEL=${GEMINI_MODEL:-gemini-1.5-pro}

# Celery / Redis Settings
REDIS_URL=redis://localhost:6379/0

# Production Settings
ALLOWED_HOSTS=$DOMAIN,www.$DOMAIN,127.0.0.1,localhost
EOL
fi

# Run Django migrations
echo "Running database migrations..."
cd $APP_DIR
$VENV_DIR/bin/python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
$VENV_DIR/bin/python manage.py collectstatic --noinput
EOF

# Configure Gunicorn
echo "Configuring Gunicorn..."
cp $APP_DIR/deployment/gunicorn.service /etc/systemd/system/gunicorn.service
systemctl enable gunicorn
systemctl restart gunicorn

# Configure Celery Worker
echo "Configuring Celery Worker..."
cp $APP_DIR/deployment/celery.service /etc/systemd/system/celery.service
systemctl enable celery
systemctl restart celery

# Configure Celery Beat
echo "Configuring Celery Beat..."
cp $APP_DIR/deployment/celerybeat.service /etc/systemd/system/celerybeat.service
systemctl enable celerybeat
systemctl restart celerybeat

# Configure Nginx
echo "Configuring Nginx..."
cp $APP_DIR/deployment/nginx.conf /etc/nginx/sites-available/blogify
# Replace placeholder domain with actual domain
sed -i "s/yourdomain.com/$DOMAIN/g" /etc/nginx/sites-available/blogify
ln -sf /etc/nginx/sites-available/blogify /etc/nginx/sites-enabled/
systemctl restart nginx

echo "Deployment completed successfully!"
echo "Your blog site should now be accessible at http://$DOMAIN" 