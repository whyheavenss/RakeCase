from email import message
import os
import sqlite3
import random
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import CommandStart
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

TOKEN = os.environ.get('TG_BOT_TOKEN', '8318517820:AAGGlOpR5-U9VR8tDfSyVKNO_iSBwFI4dh0')

# --- База данных ---
conn = sqlite3.connect('bot_data.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    gifts TEXT DEFAULT ''
)''')
conn.commit()

def ensure_user(user_id: int):
    cur.execute('INSERT OR IGNORE INTO users(user_id) VALUES(?)', (user_id,))
    conn.commit()

# --- Aiogram 3 ---
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

@router.message(CommandStart())
async def start_cmd(message: types.Message):
    ensure_user(message.from_user.id)

    web_app_url = "https://rake-case.vercel.app"  # <- обязательно с http(s)://
    keyboard_dict = {
        "inline_keyboard": [
            [
                {
                    "text": "🔥 Открывать кейсы",
                    "web_app": {"url": web_app_url}
                }
            ]
        ]
    }

    await message.answer(
        "🎁 Привет, крути кейсы и получай NFT-подарки!",
        reply_markup=keyboard_dict
    )

# --- Веб-сервер ---
routes = web.RouteTableDef()

@routes.get('/')
async def index(req):
    return web.FileResponse('index.html')

@routes.get('/static/{fname}')
async def static_files(req):
    fname = req.match_info['fname']
    return web.FileResponse(os.path.join('static', fname))

# API: баланс
@routes.get('/api/me')
async def api_me(req):
    user_id = int(req.cookies.get('uid', '123456789'))
    ensure_user(user_id)
    cur.execute('SELECT balance FROM users WHERE user_id=?', (user_id,))
    balance = cur.fetchone()[0]
    return web.json_response({'balance': balance})

# API: пополнение
@routes.post('/api/topup')
async def api_topup(req):
    user_id = int(req.cookies.get('uid', '123456789'))
    ensure_user(user_id)
    cur.execute('UPDATE users SET balance = balance + 10 WHERE user_id=?', (user_id,))
    conn.commit()
    return web.json_response({'ok': True, 'message': 'Баланс пополнен на 10⭐'})

# API: открытие кейса
@routes.post('/api/open')
async def api_open(req):
    user_id = int(req.cookies.get('uid', '123456789'))
    ensure_user(user_id)
    cur.execute('SELECT balance FROM users WHERE user_id=?', (user_id,))
    balance = cur.fetchone()[0]
    if balance < 10:
        return web.json_response({'ok': False, 'message': 'Недостаточно средств'})

    gifts = ['NFT-Обычный', 'NFT-Редкий', 'NFT-Эпик', 'NFT-Легендарный']
    weights = [70, 20, 8, 2]
    gift = random.choices(gifts, weights)[0]

    cur.execute('UPDATE users SET balance = balance - 10 WHERE user_id=?', (user_id,))
    cur.execute('UPDATE users SET gifts = gifts || ? || "," WHERE user_id=?', (gift, user_id))
    conn.commit()
    return web.json_response({'ok': True, 'message': f'Вы получили: {gift}'})

# API: подарки
@routes.get('/api/gifts')
async def api_gifts(req):
    user_id = int(req.cookies.get('uid', '123456789'))
    ensure_user(user_id)
    cur.execute('SELECT gifts FROM users WHERE user_id=?', (user_id,))
    row = cur.fetchone()[0]
    gifts = [g for g in row.split(',') if g]
    return web.json_response({'gifts': gifts})

async def start_web():
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("WebApp running at http://0.0.0.0:8080")

async def main():
    asyncio.create_task(start_web())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
