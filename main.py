import os, asyncio, json, aiohttp
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

bot = Bot(token=os.environ["BOT_TOKEN"])
dp = Dispatcher()
WEBAPP_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SB_URL = os.environ["SUPABASE_URL"].rstrip("/")
SB_KEY = os.environ["SUPABASE_KEY"]
HEADERS = {"apikey": SB_KEY, "Content-Type": "application/json", "Prefer": "return=representation"}


async def sb(method, table, params=None, body=None):
    async with aiohttp.ClientSession() as s:
        async with s.request(method, f"{SB_URL}/rest/v1/{table}", headers=HEADERS, params=params, json=body) as r:
            text = await r.text()
            if r.status >= 300:
                raise Exception(text[:200])
            return json.loads(text) if text else []


@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Open App", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])
    await message.answer("স্বাগতম! নিচের বাটনে চাপুন 👇", reply_markup=kb)


@dp.message(Command("admin", "rates", "setrate", "toggle", "addcoin", "delcoin"))
async def admin_cmd(m: Message, command: CommandObject):
    if m.from_user.id != ADMIN_ID:
        return
    cmd = command.command
    parts = (command.args or "").split()
    try:
        if cmd == "admin":
            await m.answer(
                "অ্যাডমিন কমান্ড:\n"
                "/rates - সব রেট দেখুন\n"
                "/setrate NAME 22 - দাম বদলান\n"
                "/toggle NAME - চালু/বন্ধ করুন\n"
                "/addcoin NAME 15 - নতুন কয়েন\n"
                "/delcoin NAME - কয়েন মুছুন\n"
                "উদাহরণ: /setrate NS COIN 12"
            )
        elif cmd == "rates":
            rows = await sb("GET", "rates", params={"select": "*", "order": "rate.desc"})
            lines = [f"{'🟢' if r['active'] else '🔴'} {r['name']}: {r['rate']}৳" for r in rows]
            await m.answer("\n".join(lines) or "কোনো কয়েন নেই")
        elif cmd in ("setrate", "addcoin"):
            if len(parts) < 2:
                await m.answer(f"ব্যবহার: /{cmd} NAME 20")
                return
            rate = float(parts[-1])
            name = " ".join(parts[:-1]).upper()
            if cmd == "setrate":
                res = await sb("PATCH", "rates", params={"name": f"eq.{name}"}, body={"rate": rate})
                await m.answer(f"✅ {name} = {rate}৳" if res else "❌ এই নামের কয়েন নেই")
            else:
                await sb("POST", "rates", body={"name": name, "rate": rate, "active": True})
                await m.answer(f"✅ {name} যোগ হয়েছে ({rate}৳)")
        elif cmd == "toggle":
            name = " ".join(parts).upper()
            rows = await sb("GET", "rates", params={"name": f"eq.{name}"})
            if not rows:
                await m.answer("❌ এই নামের কয়েন নেই")
                return
            new = not rows[0]["active"]
            await sb("PATCH", "rates", params={"name": f"eq.{name}"}, body={"active": new})
            await m.answer(f"{name}: {'🟢 চালু (Active)' if new else '🔴 বন্ধ (Buy Stop)'}")
        elif cmd == "delcoin":
            name = " ".join(parts).upper()
            res = await sb("DELETE", "rates", params={"name": f"eq.{name}"})
            await m.answer(f"🗑️ {name} মুছে গেছে" if res else "❌ এই নামের কয়েন নেই")
    except ValueError:
        await m.answer("❌ দামটা সংখ্যায় লিখুন, যেমন: /setrate NS COIN 12")
    except Exception as e:
        await m.answer(f"ত্রুটি: {e}")


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
    try:
        return await sb("GET", "rates", params={"select": "*", "order": "rate.desc"})
    except Exception:
        return []
