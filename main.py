import os, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

bot = Bot(token=os.environ["BOT_TOKEN"])
dp = Dispatcher()
WEBAPP_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

RATES = [
    {"name": "COINSTA", "rate": 20, "active": True},
    {"name": "TOPFOLLOWER", "rate": 18, "active": True},
    {"name": "NS COIN", "rate": 10, "active": True},
    {"name": "NIVA COIN", "rate": 4, "active": False},
]

@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Open App", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])
    await message.answer("স্বাগতম! নিচের বাটনে চাপুন 👇", reply_markup=kb)

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(dp.start_polling(bot))
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.api_route("/", methods=["GET", "HEAD"])
async def home():
    return FileResponse("index.html")

@app.get("/api/rates")
async def rates():
    return RATES
