# Hotmail/Xbox Checker Telegram Bot

A Telegram bot for checking Hotmail accounts and Xbox/Minecraft entitlements with dual checker support.

## Features

### 1. **Dual Checker System**
- **📥 Inboxer Checker**: Checks Hotmail accounts for linked services
- **🎮 Xbox Checker**: Checks Xbox/Minecraft accounts for entitlements with 1/3 retry chance

### 2. **User Interface**
- Checker selection buttons when uploading files
- Live terminal logging for Xbox checker
- Real-time status updates in Telegram

### 3. **File Handling**
- ZIP file delivery with all required hit categories
- 6000 line limit for non-admin users
- No limit for admin users
- Automatic cleanup of old files

### 4. **Admin Features**
- Admin panel (`/adm` command)
- Broadcast messages to all users
- View statistics and active checks
- Export user list
- Toggle maintenance mode

## Installation

### Quick Start
```bash
# Run the installation script
./install.sh

# Or install manually
pip install -r requirements.txt
```

### Manual Installation
1. Clone or download the project
2. Install Python 3.8+ if not already installed
3. Install dependencies:
   ```bash
   pip install pyTelegramBotAPI requests pycountry colorama urllib3
   ```
4. Configure the bot:
   ```bash
   cp config.py.example config.py
   # Edit config.py and add your BOT_TOKEN
   ```

## Configuration

Edit `config.py` with your settings:

```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Get from @BotFather
BOT_NAME = "Hotmail Inboxer"
ADMIN_IDS = {7265489223}  # Your Telegram user ID

MAX_LINES = 6000  # Max lines per check for non-admin users
DEFAULT_THREADS = 50  # Default threads for checking
MAX_THREADS = 100  # Maximum allowed threads
```

## Usage

### Starting the Bot
```bash
python bot.py
```

### User Commands
- `/start` - Welcome message and instructions
- Upload `.txt` file with `email:password` combos
- Select checker type (Inboxer or Xbox)
- Receive results as ZIP file

### Admin Commands
- `/status` - View bot statistics
- `/adm` - Open admin panel
- `/broadcast` - Send message to all users (reply to message)
- `/fetch_all` - Export user list

## File Structure

```
hot/
├── bot.py                 # Main bot application
├── config.py             # Configuration settings
├── hotmail_checker.py    # Inboxer checker implementation
├── xbox_checker.py       # Xbox/Minecraft checker
├── stats.py              # Statistics and user management
├── requirements.txt      # Production dependencies
├── requirements-dev.txt  # Development dependencies
├── install.sh           # Installation script
├── README.md            # This file
├── sample_combos.txt    # Example combo file
├── test_checkers.py     # Test suite
├── test_bot_init.py     # Bot initialization test
└── demo_bot_workflow.py # Workflow demonstration
```

## Checker Types

### Inboxer Checker
- Checks for linked services in Hotmail accounts
- Categories hits by service type
- Returns ZIP with categorized files

### Xbox Checker
- Checks Xbox/Minecraft entitlements
- 1/3 chance for retry on errors
- Live terminal logging
- Returns ZIP with 7 required files:
  1. `Hits.txt` - All successful hits
  2. `Capture.txt` - Detailed capture info
  3. `XboxGamePassUltimate.txt` - XGPU accounts
  4. `XboxGamePass.txt` - XGP accounts
  5. `Other.txt` - Other account types
  6. `2FA.txt` - Accounts requiring 2FA
  7. `Not_Found.txt` - Successful logins without Minecraft

## Testing

Run the test suite to verify functionality:

```bash
# Test both checkers
python test_checkers.py

# Test bot initialization
python test_bot_init.py

# Demo workflow
python demo_bot_workflow.py
```

## Development

### Setting up Development Environment
```bash
pip install -r requirements-dev.txt
```

### Code Style
- Follow PEP 8 guidelines
- Use Black for formatting
- Run Flake8 for linting

### Running Tests
```bash
pytest test_checkers.py
pytest test_bot_init.py
```

## Troubleshooting

### Common Issues

1. **Bot doesn't start**
   - Check `BOT_TOKEN` in config.py
   - Ensure dependencies are installed
   - Check for other running bot instances

2. **Callback query timeout**
   - Bot automatically handles old queries
   - Upload file again if selection expires

3. **File upload issues**
   - Ensure file is `.txt` format
   - Check line count (max 6000 for non-admin)
   - Verify file size (max 10MB)

4. **No hits found**
   - Verify combo format: `email:password`
   - Check account validity
   - Test with known working accounts

### Logs
- Check terminal output for live Xbox checker logs
- Look for `[BOOT]`, `[START]`, `[ERROR]` messages
- Monitor cleanup messages for old file removal

## License

This project is for educational purposes only. Use responsibly and in compliance with all applicable laws and terms of service.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the demo scripts
3. Test with sample combos
4. Check terminal logs for errors

---

**Note**: This bot is designed for legitimate account verification purposes. Always respect user privacy and comply with platform terms of service.