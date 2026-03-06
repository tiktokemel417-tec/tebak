import os
import sqlite3
import json
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# --- CONFIG ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

app = Client("bot_tebak", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- DATABASE ---
def db_query(query, params=(), fetchone=False, commit=False):
    conn = sqlite3.connect('bot_game.db')
    cursor = conn.cursor()
    cursor.execute(query, params)
    if commit: conn.commit()
    res = cursor.fetchone() if fetchone else cursor.fetchall()
    conn.close()
    return res

def init_db():
    conn = sqlite3.connect('bot_game.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT, soal TEXT, jawaban TEXT, word_count INTEGER)')
    # Default Settings
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("link_dev", "https://t.me/rian_eka")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("link_sup", "https://t.me/support")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("log_group", "0")')
    conn.commit()
    conn.close()

init_db()

# --- ADMIN PANEL ---
@app.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Set Log Group", callback_data="set_log"), InlineKeyboardButton("Stats", callback_data="stats")],
        [InlineKeyboardButton("Backup DB (SendDB)", callback_data="send_db")],
        [InlineKeyboardButton("Update Links", callback_data="set_links")]
    ])
    await message.reply("🛠 **Admin Panel**\nSilakan pilih menu di bawah:", reply_markup=kb)

@app.on_callback_query(filters.regex("send_db"))
async def handle_senddb(client, callback_query: CallbackQuery):
    await callback_query.message.reply_document("bot_game.db", caption="Ini database terbaru lo.")
    await callback_query.answer("DB Sent!")

# --- FEATURE: UPDATE DB (ANTI-RESET RAILWAY) ---
@app.on_message(filters.command("update") & filters.user(OWNER_ID) & filters.reply)
async def sync_db(client, message):
    if not message.reply_to_message.document:
        return await message.reply("Reply file .db nya!")
    
    path = await message.reply_to_message.download("temp_old.db")
    old_conn = sqlite3.connect(path)
    new_conn = sqlite3.connect("bot_game.db")
    
    # Sync Users (Hanya tambah yang belum ada)
    users = old_conn.execute("SELECT * FROM users").fetchall()
    for u in users:
        new_conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", u)
    
    # Sync Questions
    qs = old_conn.execute("SELECT * FROM questions").fetchall()
    for q in qs:
        new_conn.execute("INSERT OR IGNORE INTO questions (soal, jawaban, word_count) VALUES (?, ?, ?)", (q[1], q[2], q[3]))
        
    new_conn.commit()
    await message.reply("✅ Sinkronisasi Berhasil! Data lama sudah digabung.")

# --- LOBBY SYSTEM (BASIC) ---
lobbies = {} # {chat_id: {"host": id, "players": [ids]}}

@app.on_message(filters.command("mulai") & filters.group)
async def start_lobby(client, message):
    chat_id = message.chat.id
    if chat_id in lobbies:
        return await message.reply("Lobi sudah terbuka!")
    
    lobbies[chat_id] = {"host": message.from_user.id, "players": [message.from_user.id]}
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Gabung ➕", callback_data="join_lobby")],
        [InlineKeyboardButton("Mulai Game ▶️", callback_data="start_game")]
    ])
    await message.reply(f"🎮 **Lobi Dibuka!**\nHost: {message.from_user.first_name}\nPemain: 1/3", reply_markup=kb)

@app.on_callback_query(filters.regex("join_lobby"))
async def join_handler(client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id
    
    if chat_id not in lobbies: return await callback_query.answer("Lobi sudah tutup.")
    if user_id in lobbies[chat_id]["players"]: return await callback_query.answer("Lo udah join!")
    if len(lobbies[chat_id]["players"]) >= 3: return await callback_query.answer("Lobi penuh!")
    
    lobbies[chat_id]["players"].append(user_id)
    count = len(lobbies[chat_id]["players"])
    
    await callback_query.message.edit_text(
        f"🎮 **Lobi Dibuka!**\nPemain: {count}/3\nDaftar: " + ", ".join([str(p) for p in lobbies[chat_id]["players"]]),
        reply_markup=callback_query.message.reply_markup
    )
    await callback_query.answer("Berhasil gabung!")

# Lanjut run...
app.run()
