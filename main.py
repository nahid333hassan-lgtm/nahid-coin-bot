import os, asyncio, json, hmac, hashlib, time, aiohttp
from urllib.parse import parse_qsl
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup,
                           InlineKeyboardButton, WebAppInfo)

BOT_TOKEN = os.environ["BOT_TOKEN"]
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
WEBAPP_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
SB_URL = os.environ["SUPABASE_URL"].rstrip("/")
SB_KEY = os.environ["SUPABASE_KEY"]
HEADERS = {"apikey": SB_KEY, "Content-Type": "application/json", "Prefer": "return=representation"}
METHODS = ["bKash", "Nagad", "Rocket", "USDT BEP20"]


async def sb(method, table, params=None, body=None):
    async with aiohttp.ClientSession() as s:
        async with s.request(method, f"{SB_URL}/rest/v1/{table}", headers=HEADERS, params=params, json=body) as r:
            text = await r.text()
            if r.status >= 300:
                raise Exception(text[:200])
            return json.loads(text) if text else []


def verify_init(init_data: str):
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        got = data.pop("hash")
        check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got):
            raise ValueError("bad hash")
        if time.time() - int(data["auth_date"]) > 86400:
            raise ValueError("expired")
        return json.loads(data["user"])
    except Exception:
        raise HTTPException(status_code=401, detail="লগইন যাচাই হয়নি। অ্যাপটি বন্ধ করে বট থেকে আবার খুলুন।")


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


@dp.callback_query(F.data.regexp(r"^(ok|no):\d+$"))
async def decide(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("আপনার অনুমতি নেই", show_alert=True)
        return
    action, tid = cb.data.split(":")
    status = "approved" if action == "ok" else "rejected"
    try:
        rows = await sb("PATCH", "transactions",
                        params={"id": f"eq.{tid}", "status": "eq.pending"},
                        body={"status": status})
    except Exception as e:
        await cb.answer(f"ত্রুটি: {e}", show_alert=True)
        return
    if not rows:
        await cb.answer("এটার সিদ্ধান্ত আগেই নেওয়া হয়েছে", show_alert=True)
        return
    t = rows[0]
    label = "✅ Approved" if status == "approved" else "❌ Rejected"
    try:
        await cb.message.edit_text(f"{cb.message.text}\n\n{label}")
    except Exception:
        pass
    if status == "approved":
        msg = f"✅ রিকোয়েস্ট #{t['id']} সম্পন্ন হয়েছে। {t['total']}৳ আপনার {t['payment_method']}-এ পাঠানো হয়েছে।"
    else:
        msg = f"❌ রিকোয়েস্ট #{t['id']} বাতিল হয়েছে। কয়েন না পেলে বা তথ্য ভুল হলে এমন হয়। সাপোর্টে যোগাযোগ করুন।"
    try:
        await bot.send_message(t["tg_user_id"], msg)
    except Exception:
        pass
    await cb.answer("হয়েছে")


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(dp.start_polling(bot))
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


class Init(BaseModel):
    init: str


class Sell(BaseModel):
    init: str
    coin: str
    amount: int
    method: str
    number: str
    note: str = ""


@app.api_route("/", methods=["GET", "HEAD"])
async def home():
    return FileResponse("index.html")


@app.get("/api/rates")
async def rates():
    try:
        return await sb("GET", "rates", params={"select": "*", "order": "rate.desc"})
    except Exception:
        return []


@app.post("/api/history")
async def history(d: Init):
    user = verify_init(d.init)
    return await sb("GET", "transactions", params={
        "tg_user_id": f"eq.{user['id']}", "order": "created_at.desc", "limit": "30",
        "select": "id,coin,amount,total,payment_method,payment_number,status,created_at"})


@app.post("/api/sell")
async def sell(d: Sell):
    user = verify_init(d.init)
    number = d.number.strip()[:60]
    note = d.note.strip()[:200]
    if d.amount < 1000 or d.amount > 10_000_000:
        raise HTTPException(400, "পরিমাণ কমপক্ষে ১০০০ হতে হবে")
    if d.method not in METHODS:
        raise HTTPException(400, "পেমেন্ট মাধ্যম ঠিক নেই")
    if not number:
        raise HTTPException(400, "পেমেন্ট নম্বর দিন")
    rows = await sb("GET", "rates", params={"name": f"eq.{d.coin.upper()}"})
    if not rows or not rows[0]["active"]:
        raise HTTPException(400, "এই কয়েন এখন নেওয়া হচ্ছে না")
    pend = await sb("GET", "transactions", params={
        "tg_user_id": f"eq.{user['id']}", "status": "eq.pending", "select": "id"})
    if len(pend) >= 5:
        raise HTTPException(400, "আপনার ৫টি রিকোয়েস্ট অপেক্ষায় আছে, আগে সেগুলো শেষ হোক")
    total = round(d.amount / 1000 * float(rows[0]["rate"]), 2)
    res = await sb("POST", "transactions", body={
        "tg_user_id": user["id"], "coin": rows[0]["name"], "amount": d.amount,
        "total": total, "payment_method": d.method, "payment_number": number, "note": note})
    t = res[0]
    uname = f"@{user['username']}" if user.get("username") else "-"
    text = (f"🆕 নতুন রিকোয়েস্ট #{t['id']}\n"
            f"👤 {user.get('first_name', '')} ({uname}) ID: {user['id']}\n"
            f"🪙 {t['coin']}: {d.amount} কয়েন\n"
            f"💰 {total}৳\n"
            f"💳 {d.method}: {number}\n"
            f"📝 {note or '-'}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Approve", callback_data=f"ok:{t['id']}"),
        InlineKeyboardButton(text="❌ Reject", callback_data=f"no:{t['id']}")]])
    try:
        await bot.send_message(ADMIN_ID, text, reply_markup=kb)
    except Exception:
        pass
    return {"ok": True, "id": t["id"], "total": total}
