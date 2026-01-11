#!/usr/bin/env python3
"""
Telegram Bot for WWII History Video Production
Triggers GitHub Actions workflow via repository_dispatch
"""

import os
import json
import requests
import time
from datetime import datetime
from flask import Flask, request, jsonify

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_WEBHOOK_URL = os.environ.get('TELEGRAM_WEBHOOK_URL')  # Your server URL
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO')  # format: username/repo
AUTHORIZED_CHAT_IDS = os.environ.get('TELEGRAM_CHAT_ID', '').split(',')

app = Flask(__name__)

class TelegramBot:
    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        self.github_api = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
        
    def send_message(self, chat_id, text, reply_markup=None):
        """Send message to Telegram"""
        url = f"{self.base_url}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        if reply_markup:
            data['reply_markup'] = json.dumps(reply_markup)
        
        try:
            response = requests.post(url, json=data, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Error sending message: {e}")
            return None
    
    def trigger_github_workflow(self, video_data):
        """Trigger GitHub Actions workflow via repository_dispatch"""
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        payload = {
            'event_type': 'create_video',
            'client_payload': video_data
        }
        
        try:
            response = requests.post(self.github_api, json=payload, headers=headers, timeout=15)
            if response.status_code == 204:
                print(f"✅ Workflow triggered successfully")
                return True
            else:
                print(f"❌ Failed to trigger workflow: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error triggering workflow: {e}")
            return False
    
    def save_production_request(self, chat_id, message_data):
        """Save production request to file"""
        video_id = f"video_{int(time.time())}"
        
        production_data = {
            'video_id': video_id,
            'chat_id': chat_id,
            'timestamp': datetime.now().isoformat(),
            'script': message_data.get('script', ''),
            'title': message_data.get('title', ''),
            'description': message_data.get('description', ''),
            'tags': message_data.get('tags', []),
            'status': 'pending'
        }
        
        # Save to productions directory
        os.makedirs('productions', exist_ok=True)
        filepath = f'productions/{video_id}.json'
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(production_data, f, indent=2, ensure_ascii=False)
        
        return production_data
    
    def parse_production_message(self, text):
        """Parse production message from Telegram"""
        lines = text.strip().split('\n')
        
        data = {
            'script': '',
            'title': '',
            'description': '',
            'tags': []
        }
        
        current_section = None
        
        for line in lines:
            line = line.strip()
            
            if line.upper().startswith('TITLE:'):
                current_section = 'title'
                data['title'] = line[6:].strip()
            elif line.upper().startswith('DESCRIPTION:'):
                current_section = 'description'
                data['description'] = line[12:].strip()
            elif line.upper().startswith('TAGS:'):
                current_section = 'tags'
                tags_str = line[5:].strip()
                data['tags'] = [t.strip() for t in tags_str.split(',')]
            elif line.upper().startswith('SCRIPT:'):
                current_section = 'script'
                data['script'] = line[7:].strip()
            else:
                if current_section == 'script':
                    data['script'] += '\n' + line
                elif current_section == 'description':
                    data['description'] += '\n' + line
        
        # Clean up
        data['script'] = data['script'].strip()
        data['description'] = data['description'].strip()
        
        return data

bot = TelegramBot()

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Telegram webhook"""
    try:
        update = request.get_json()
        
        if 'message' in update:
            message = update['message']
            chat_id = str(message['chat']['id'])
            
            # Check authorization
            if chat_id not in AUTHORIZED_CHAT_IDS:
                bot.send_message(chat_id, "⛔ Unauthorized access")
                return jsonify({'ok': True})
            
            text = message.get('text', '')
            
            # Handle commands
            if text.startswith('/start'):
                bot.send_message(
                    chat_id,
                    "🎬 <b>WWII History Video Production Bot</b>\n\n"
                    "📝 <b>How to create a video:</b>\n\n"
                    "Send your production request in this format:\n\n"
                    "<code>TITLE: Your video title\n"
                    "DESCRIPTION: Your video description\n"
                    "TAGS: tag1, tag2, tag3\n"
                    "SCRIPT:\n"
                    "Your complete narration script here...</code>\n\n"
                    "The bot will:\n"
                    "1️⃣ Generate audio from script\n"
                    "2️⃣ Request media for each 30s segment\n"
                    "3️⃣ Create and upload the video\n\n"
                    "🔔 Commands:\n"
                    "/start - Show this message\n"
                    "/status - Check production status"
                )
                
            elif text.startswith('/status'):
                # TODO: Implement status check
                bot.send_message(chat_id, "📊 Status check not yet implemented")
                
            elif text.startswith('TITLE:') or text.startswith('title:'):
                # Production request
                bot.send_message(chat_id, "📋 Processing your production request...")
                
                # Parse message
                message_data = bot.parse_production_message(text)
                
                # Validate
                if not message_data['script']:
                    bot.send_message(chat_id, "❌ No script found. Please include SCRIPT: section")
                    return jsonify({'ok': True})
                
                if not message_data['title']:
                    message_data['title'] = f"WWII Story - {datetime.now().strftime('%Y-%m-%d')}"
                
                # Save production request
                production_data = bot.save_production_request(chat_id, message_data)
                
                # Trigger GitHub workflow
                success = bot.trigger_github_workflow(production_data)
                
                if success:
                    bot.send_message(
                        chat_id,
                        f"✅ <b>Production Started!</b>\n\n"
                        f"🎬 Video ID: <code>{production_data['video_id']}</code>\n"
                        f"📝 Title: {production_data['title']}\n"
                        f"⏱️ Script length: {len(production_data['script'])} chars\n\n"
                        f"🔄 GitHub Actions workflow triggered\n"
                        f"📱 You'll receive media requests soon..."
                    )
                else:
                    bot.send_message(
                        chat_id,
                        "❌ <b>Failed to start production</b>\n\n"
                        "Please check GitHub Actions or contact support."
                    )
            else:
                bot.send_message(
                    chat_id,
                    "❓ Unknown command\n\n"
                    "Use /start to see instructions"
                )
        
        return jsonify({'ok': True})
        
    except Exception as e:
        print(f"Error in webhook: {e}")
        return jsonify({'ok': False, 'error': str(e)})

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

def setup_webhook():
    """Setup Telegram webhook"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    data = {'url': f"{TELEGRAM_WEBHOOK_URL}/webhook"}
    
    response = requests.post(url, json=data)
    result = response.json()
    
    if result.get('ok'):
        print(f"✅ Webhook set successfully: {TELEGRAM_WEBHOOK_URL}/webhook")
    else:
        print(f"❌ Failed to set webhook: {result}")

if __name__ == '__main__':
    # Setup webhook on startup
    if TELEGRAM_WEBHOOK_URL:
        setup_webhook()
    
    # Run Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
