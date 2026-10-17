import os, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

bot = Bot(token=os.environ["BOT_TOKEN"])
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("স্বাগতম! বট চালু আছে ✅")

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(dp.start_polling(bot))
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)

@app.api_route("/", methods=["GET", "HEAD"])
async def home():
    return {"status": "ok"}
