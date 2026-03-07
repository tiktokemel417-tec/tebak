import os
import sqlite3
import random
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    CallbackQuery, 
    BotCommand, 
    BotCommandScopeChat, 
    BotCommandScopeAllGroupChats
)

# --- CONFIG ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

app = Client("bot_tebak", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- DATABASE LOGIC ---
def init_db():
    conn = sqlite3.connect('bot_game.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS questions (id INTEGER PRIMARY KEY AUTOINCREMENT, soal TEXT, jawaban TEXT, word_count INTEGER)')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("link_dev", "https://t.me/rian_eka")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("link_sup", "https://t.me/support")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("log_group", "0")')
    conn.commit()
    conn.close()

def db_execute(query, params=(), commit=False, fetchone=False):
    conn = sqlite3.connect('bot_game.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(query, params)
    if commit: conn.commit()
    res = cursor.fetchone() if fetchone else cursor.fetchall()
    conn.close()
    return res

def seed_questions():
    check = db_execute("SELECT COUNT(*) FROM questions", fetchone=True)[0]
    if check == 0:
        data = [
            ("Ibukota Jawa Barat", "Kota,Bandung", 2),
            ("Warna bendera Indonesia", "Merah,Putih", 2),
            ("Singkatan dari Air Susu Ibu", "Air,Susu,Ibu", 3),
            ("Tempat parkir pesawat", "Bandara,Udara", 2),
            ("Alat transportasi rel", "Kereta,Api,Listrik", 3)
        ]
        conn = sqlite3.connect('bot_game.db')
        conn.executemany("INSERT INTO questions (soal, jawaban, word_count) VALUES (?, ?, ?)", data)
        conn.commit()
        conn.close()

# --- GLOBAL VARIABLES ---
lobbies = {} 
games = {}   

# --- HELPER FUNCTIONS ---
async def send_log(client, text):
    log_id_data = db_execute("SELECT value FROM settings WHERE key='log_group'", fetchone=True)
    if log_id_data and log_id_data[0] != "0":
        try:
            await client.send_message(int(log_id_data[0]), text)
        except:
            pass

# --- HANDLERS ---

@app.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Statistik", callback_data="stats"), InlineKeyboardButton("📂 Backup DB", callback_data="send_db")],
        [InlineKeyboardButton("🔗 Set Log Group", callback_data="set_log")]
    ])
    await message.reply("🛠 **Admin Control Panel**", reply_markup=kb)

@app.on_message(filters.command("addsoal") & filters.user(OWNER_ID))
async def add_soal(client, message):
    try:
        data = message.text.split(None, 1)[1]
        soal, jawaban = data.split("|")
        soal, jawaban = soal.strip(), jawaban.strip()
        word_count = len(jawaban.split(","))
        db_execute("INSERT INTO questions (soal, jawaban, word_count) VALUES (?, ?, ?)", (soal, jawaban, word_count), commit=True)
        await message.reply(f"✅ **Soal Ditambah!**\n💬 {soal}\n📝 {word_count} Kata")
    except:
        await message.reply("❌ Format: `/addsoal Soal | Kata1,Kata2`")

@app.on_message(filters.command("setlog") & filters.user(OWNER_ID))
async def set_log_handler(client, message):
    try:
        log_id = message.command[1]
        db_execute("UPDATE settings SET value = ? WHERE key = 'log_group'", (log_id,), commit=True)
        await client.send_message(int(log_id), "✅ Grup ini diset sebagai Log Group.")
        await message.reply(f"✅ Log Group diset ke `{log_id}`")
    except:
        await message.reply("❌ Contoh: `/setlog -100xxxx`")

@app.on_message(filters.command("start") & filters.private)
async def start_private(client, message):
    user = message.from_user
    db_execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.username), commit=True)
    await send_log(client, f"👤 **User Start Bot**\n{user.mention} (`{user.id}`)")
    await message.reply(f"Halo {user.first_name}! Masukkan bot ke grup untuk mulai main `/mulai`.")

@app.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if data == "stats":
        u_count = db_execute("SELECT COUNT(*) FROM users", fetchone=True)[0]
        q_count = db_execute("SELECT COUNT(*) FROM questions", fetchone=True)[0]
        await callback_query.answer(f"Stats: {u_count} User, {q_count} Soal", show_alert=True)

    elif data == "send_db":
        if user_id == OWNER_ID:
            await callback_query.message.reply_document("bot_game.db")

    elif data == "set_log":
        await callback_query.message.edit_text("Ketik `/setlog ID_GRUP` untuk menyetel log group.")

    elif data == "join_lobby":
        if chat_id not in lobbies: return await callback_query.answer("Lobi hangus!")
        if user_id in lobbies[chat_id]["players"]: return await callback_query.answer("Udah join!")
        lobbies[chat_id]["players"].append(user_id)
        current = len(lobbies[chat_id]["players"])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Gabung ({current}/3)", callback_data="join_lobby")], [InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
        await callback_query.message.edit_text(f"🎮 **Lobi Terbuka!**\nPemain: {current}/3", reply_markup=kb)

    elif data == "start_game":
        if chat_id not in lobbies: return
        p_list = lobbies[chat_id]["players"]
        if len(p_list) < 2: return await callback_query.answer("Minimal 2 orang!")
        
        qs = db_execute("SELECT soal, jawaban FROM questions WHERE word_count = ?", (len(p_list),))
        if not qs: return await callback_query.answer("Soal tdk ditemukan!")
        
        q = random.choice(qs)
        games[chat_id] = {"soal": q[0], "jawaban": q[1].split(","), "turn": 0, "players": p_list}
        del lobbies[chat_id]
        
        p_info = await client.get_users(p_list[0])
        await callback_query.message.edit_text(f"🚀 **GAME MULAI!**\n❓ Soal: {q[0]}\n👉 Giliran: {p_info.mention}")

@app.on_message(filters.group & filters.text & ~filters.command(["mulai", "stop", "top", "start", "admin"]))
async def check_answer(client, message):
    chat_id = message.chat.id
    if chat_id not in games: return
    game = games[chat_id]
    if message.from_user.id != game["players"][game["turn"]]: return
    
    if message.text.strip().lower() == game["jawaban"][game["turn"]].lower():
        game["turn"] += 1
        if game["turn"] >= len(game["jawaban"]):
            for pid in game["players"]:
                db_execute("UPDATE users SET points = points + 10 WHERE user_id = ?", (pid,), commit=True)
            await message.reply("✅ **MENANG!** +10 poin!")
            del games[chat_id]
        else:
            p_next = await client.get_users(game["players"][game["turn"]])
            await message.reply(f"✅ Bener! Lanjut {p_next.mention}")

@app.on_message(filters.command("mulai") & filters.group)
async def start_lobby(client, message):
    lobbies[message.chat.id] = {"host": message.from_user.id, "players": [message.from_user.id]}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Gabung ➕", callback_data="join_lobby")], [InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
    await message.reply("🎮 **Lobi Dibuka!**", reply_markup=kb)

@app.on_message(filters.command("update") & filters.user(OWNER_ID) & filters.reply)
async def update_db_manual(client, message):
    if not message.reply_to_message.document: return
    path = await message.reply_to_message.download("temp.db")
    conn = sqlite3.connect(path); curr = conn.cursor()
    new_qs = curr.execute("SELECT soal, jawaban, word_count FROM questions").fetchall()
    added = 0
    for q in new_qs:
        if not db_execute("SELECT id FROM questions WHERE soal = ?", (q[0],), fetchone=True):
            db_execute("INSERT INTO questions (soal, jawaban, word_count) VALUES (?, ?, ?)", q, commit=True)
            added += 1
    os.remove(path)
    await message.reply(f"✅ Berhasil nambah {added} soal baru!")

@app.on_message(filters.new_chat_members)
async def bot_added_logger(client, message):
    me = await client.get_me()
    if any(m.id == me.id for m in message.new_chat_members):
        chat = message.chat
        log_text = f"➕ **BOT ADDED**\n🏰 {chat.title}\n🆔 `{chat.id}`\n👤 By: {message.from_user.mention}"
        await client.send_message(OWNER_ID, log_text)
        await send_log(client, log_text)

# --- STARTUP ---
async def start_bot():
    await app.start()
    print("🚀 Bot Tebak Berantai is Running!")
    await idle()

if __name__ == "__main__":
    init_db(); seed_questions()
    app.run(start_bot())
