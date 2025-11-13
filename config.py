import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN=os.getenv('BOT_TOKEN','')
DB_URL=os.getenv('DB_URL','sqlite+aiosqlite:///./bot.db')
STORAGE_ROOT=os.getenv('STORAGE_ROOT','./storage')
BOOTSTRAP_ADMIN_IDS=[int(x) for x in os.getenv('BOOTSTRAP_ADMIN_IDS','').replace(' ','').split(',') if x]
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0") or 0)