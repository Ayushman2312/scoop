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

# Check if API keys are provided as environment variables
if [ -z "$SERPAPI_KEY" ] || [ -z "$GEMINI_KEY" ]; then
    echo "Error: Both SERPAPI_KEY and GEMINI_KEY environment variables must be set."
    echo "Usage: SERPAPI_KEY=your_key GEMINI_KEY=your_key $0"
    exit 1
fi

# Switch to www-data user for command execution
sudo -u www-data bash << EOF
cd $APP_DIR
echo "Initializing API keys..."
$VENV_DIR/bin/python manage.py setup_keys --serpapi-key="$SERPAPI_KEY" --gemini-key="$GEMINI_KEY"
EOF

echo "API keys have been initialized successfully!" 