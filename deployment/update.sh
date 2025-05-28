#!/bin/bash

# Exit on any error
set -e

# Configuration
APP_DIR=/var/www/blogify
VENV_DIR=$APP_DIR/venv

# Check if running as root
if [ "$(id -u)" != "0" ]; then
   echo "This script must be run as root" 1>&2
   exit 1
fi

# Switch to www-data user for repository operations
sudo -u www-data bash << EOF
echo "Updating repository..."
cd $APP_DIR
git pull

echo "Updating Python dependencies..."
$VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt

echo "Running database migrations..."
cd $APP_DIR
$VENV_DIR/bin/python manage.py migrate --noinput

echo "Collecting static files..."
$VENV_DIR/bin/python manage.py collectstatic --noinput
EOF

# Restart services
echo "Restarting services..."
systemctl restart gunicorn
systemctl restart celery
systemctl restart celerybeat

echo "Update completed successfully!" 