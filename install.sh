#!/bin/bash
# Installation script for Hotmail/Xbox Checker Bot

set -e

echo "==========================================="
echo "Hotmail/Xbox Checker Bot Installation"
echo "==========================================="

# Check Python version
echo "Checking Python version..."
python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python $python_version detected"

# Check if virtual environment should be created
read -p "Create virtual environment? (y/n): " create_venv
if [[ "$create_venv" == "y" || "$create_venv" == "Y" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Virtual environment activated"
fi

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check if development dependencies should be installed
read -p "Install development dependencies? (y/n): " install_dev
if [[ "$install_dev" == "y" || "$install_dev" == "Y" ]]; then
    echo "Installing development dependencies..."
    pip install -r requirements-dev.txt
fi

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p logs
mkdir -p data
mkdir -p temp

# Set up database
echo "Setting up database..."
if [ -f "bot.db" ]; then
    echo "Database already exists"
else
    echo "Database will be created on first run"
fi

# Create config.py if it doesn't exist
if [ ! -f "config.py" ]; then
    echo "Creating config.py from template..."
    cat > config.py << 'EOF'
# Bot Configuration
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your bot token
BOT_NAME = "Hotmail Inboxer"
ADMIN_IDS = {7265489223}  # Replace with your Telegram user ID

# Checker Settings
MAX_LINES = 6000  # Maximum lines per check for non-admin users
DEFAULT_THREADS = 50  # Default number of threads for checking
MAX_THREADS = 100  # Maximum allowed threads

# File Settings
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB maximum file size

# Retry Settings
MAX_RETRIES = 3  # Maximum number of retry attempts
RETRY_DELAY = 2  # Delay between retries in seconds

# Timeout Settings
REQUEST_TIMEOUT = 30  # HTTP request timeout in seconds
EOF
    echo "Please edit config.py and add your BOT_TOKEN"
fi

echo "==========================================="
echo "Installation complete!"
echo "==========================================="
echo ""
echo "Next steps:"
echo "1. Edit config.py and add your BOT_TOKEN"
echo "2. Run the bot: python bot.py"
echo "3. Send /start to your bot in Telegram"
echo ""
echo "For development:"
echo "- Run tests: python test_checkers.py"
echo "- Check syntax: python test_bot_init.py"
echo "- Demo workflow: python demo_bot_workflow.py"