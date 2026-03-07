import os
import sqlite3
import random
import asyncio
from pyrogram import Client, filters, idle, enums
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
    c.execute('CREATE TABLE IF NOT EXISTS groups (chat_id INTEGER PRIMARY KEY, title TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS auto_bc (id INTEGER PRIMARY KEY, msg TEXT, jam TEXT, is_on INTEGER DEFAULT 0)')
    
    defaults = [
        ("link_dev", "https://t.me/rian_eka"),
        ("link_sup", "https://t.me/support"),
        ("log_group", "0"),
        ("start_msg", "Halo! Gue bot tebak kata berantai.")
    ]
    for key, val in defaults:
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))
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

# --- GLOBAL VARIABLES ---
lobbies = {} 
games = {}   

# --- HELPER ---
async def send_log(client, text):
    log_id_data = db_execute("SELECT value FROM settings WHERE key='log_group'", fetchone=True)
    if log_id_data and log_id_data[0] != "0":
        try: await client.send_message(int(log_id_data[0]), text)
        except: pass

def get_new_question(chat_id, word_count):
    game = games.get(chat_id)
    played_ids = game.get("history", []) if game else []
    placeholders = ','.join(['?'] * len(played_ids))
    query = f"SELECT id, soal, jawaban FROM questions WHERE word_count = ?"
    if played_ids: query += f" AND id NOT IN ({placeholders})"
    res = db_execute(query, tuple([word_count] + played_ids))
    if not res:
        if game: game["history"] = []
        return db_execute("SELECT id, soal, jawaban FROM questions WHERE word_count = ?", (word_count,))
    return res

# --- HANDLERS ---

@app.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Soal", callback_data="admin_addsoal"), InlineKeyboardButton("📝 Set Start", callback_data="admin_setstart")],
        [InlineKeyboardButton("👤 Set Owner", callback_data="set_owner_link"), InlineKeyboardButton("👥 Set Support", callback_data="set_sup_link")],
        [InlineKeyboardButton("💰 Set Poin User", callback_data="admin_setpoint"), InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_bc"), InlineKeyboardButton("🆔 Set Log", callback_data="set_log")],
        [InlineKeyboardButton("📁 Send DB", callback_data="send_db"), InlineKeyboardButton("🔄 Reset Poin", callback_data="reset_all")],
        [InlineKeyboardButton("🤖 Auto BC", callback_data="admin_autobc")]
    ])
    await message.reply("🛠 **SUPER ADMIN PANEL UI**", reply_markup=kb)

@app.on_message(filters.command("start") & filters.private)
async def start_private(client, message):
    user = message.from_user
    db_execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.username), commit=True)
    await send_log(client, f"👤 #UserStart\nNama: {user.first_name}\nID: `{user.id}`\nUsername: @{user.username}")
    
    msg = db_execute("SELECT value FROM settings WHERE key='start_msg'", fetchone=True)[0]
    dev = db_execute("SELECT value FROM settings WHERE key='link_dev'", fetchone=True)[0]
    sup = db_execute("SELECT value FROM settings WHERE key='link_sup'", fetchone=True)[0]
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Dev 👨‍💻", url=dev), InlineKeyboardButton("Support 👥", url=sup)],
        [InlineKeyboardButton("➕ Tambah ke Grup", url=f"https://t.me/{client.me.username}?startgroup=true")]
    ])
    await message.reply(f"**{msg}**", reply_markup=kb)

@app.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    chat_id = callback_query.message.chat.id
    user_id = callback_query.from_user.id

    if data == "stats":
        u = db_execute("SELECT COUNT(*) FROM users", fetchone=True)[0]
        q = db_execute("SELECT COUNT(*) FROM questions", fetchone=True)[0]
        g = db_execute("SELECT COUNT(*) FROM groups", fetchone=True)[0]
        await callback_query.message.edit_text(f"📊 **STATS**\nUser: `{u}`\nGroup: `{g}`\nSoal: `{q}`", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="back_admin")]]))

    elif data == "back_admin":
        await admin_panel(client, callback_query.message)
        await callback_query.message.delete()

    elif data == "admin_autobc":
        status_data = db_execute("SELECT is_on FROM auto_bc WHERE id=1", fetchone=True)
        st = "🟢 ON" if status_data and status_data[0] == 1 else "🔴 OFF"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Status: {st}", callback_data="toggle_bc")],[InlineKeyboardButton("⬅️ Kembali", callback_data="back_admin")]])
        await callback_query.message.edit_text("⚙️ **AUTO BC SETTINGS**", reply_markup=kb)

    elif data == "toggle_bc":
        db_execute("INSERT OR IGNORE INTO auto_bc (id, is_on) VALUES (1, 0)", commit=True)
        db_execute("UPDATE auto_bc SET is_on = 1 - is_on WHERE id=1", commit=True)
        await callback_query.answer("Updated!")

    elif data == "join_lobby":
        if chat_id in games: return await callback_query.answer("Game sedang jalan!", show_alert=True)
        if chat_id not in lobbies: return await callback_query.answer("Lobi tidak aktif!")
        if user_id in lobbies[chat_id]["players"]: return await callback_query.answer("Sudah gabung!")
        lobbies[chat_id]["players"].append(user_id)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Gabung ({len(lobbies[chat_id]['players'])}/5)", callback_data="join_lobby")],[InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
        await callback_query.message.edit_text(f"🎮 **LOBI AKTIF**\nPemain: {len(lobbies[chat_id]['players'])}/5", reply_markup=kb)

    elif data == "start_game":
        if chat_id not in lobbies or len(lobbies[chat_id]["players"]) < 2: 
            return await callback_query.answer("Minimal 2 orang!", show_alert=True)
        p_list = lobbies[chat_id]["players"]
        qs = get_new_question(chat_id, len(p_list))
        if not qs: return await callback_query.answer("Soal habis!")
        q = random.choice(qs)
        games[chat_id] = {"soal": q[1], "jawaban": q[2].split(","), "turn": 0, "players": p_list, "history": [q[0]], "salah_count": 0}
        del lobbies[chat_id]
        p = await client.get_users(p_list[0])
        await callback_query.message.edit_text(f"🚀 **MULAI!**\n❓: {q[1]}\n👉: {p.mention}")

    elif data in ["admin_addsoal", "admin_setstart", "admin_bc", "set_log", "admin_setpoint", "set_owner_link", "set_sup_link"]:
        prompts = {
            "admin_addsoal": "Reply dengan: `Soal | Kata1,Kata2`",
            "admin_setstart": "Reply dengan pesan Start baru.",
            "admin_bc": "Reply dengan pesan broadcast.",
            "set_log": "Reply dengan ID Grup Log.",
            "admin_setpoint": "Reply dengan: `ID_USER | JUMLAH_POIN`",
            "set_owner_link": "Reply dengan link Telegram owner.",
            "set_sup_link": "Reply dengan link Support."
        }
        await client.send_message(chat_id, prompts[data])

@app.on_message(filters.reply & filters.user(OWNER_ID) & filters.private)
async def handle_admin_replies(client, message):
    ref = message.reply_to_message.text.lower()
    inp = message.text
    if "soal | kata1,kata2" in ref:
        s, j = inp.split("|")
        db_execute("INSERT INTO questions (soal, jawaban, word_count) VALUES (?, ?, ?)", (s.strip(), j.strip(), len(j.split(","))), commit=True)
        await message.reply("✅ Soal ditambah!")
    elif "start baru" in ref:
        db_execute("UPDATE settings SET value = ? WHERE key='start_msg'", (inp,), commit=True)
        await message.reply("✅ Start Message Updated!")
    elif "id grup log" in ref:
        db_execute("UPDATE settings SET value = ? WHERE key='log_group'", (inp,), commit=True)
        await message.reply("✅ Log Group Set!")
    elif "link telegram owner" in ref:
        db_execute("UPDATE settings SET value = ? WHERE key='link_dev'", (inp,), commit=True)
        await message.reply("✅ Owner Link Set!")
    elif "id_user | jumlah_poin" in ref:
        u, p = inp.split("|")
        db_execute("UPDATE users SET points = ? WHERE user_id = ?", (int(p.strip()), int(u.strip())), commit=True)
        await message.reply("✅ Poin Updated!")
    elif "broadcast" in ref:
        users = db_execute("SELECT user_id FROM users")
        for (uid,) in users:
            try: await client.send_message(uid, inp)
            except: pass
        await message.reply("✅ Broadcast Selesai!")

@app.on_message(filters.command("mulai") & filters.group)
async def lobby(client, message):
    if message.chat.id in games: return await message.reply("Game jalan!")
    lobbies[message.chat.id] = {"players": [message.from_user.id]}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Gabung ➕", callback_data="join_lobby")],[InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
    await message.reply("🎮 **LOBI TEBAK BERANTAI**", reply_markup=kb)

@app.on_message(filters.group & filters.text & ~filters.command(["mulai", "stop", "top", "help", "keluar"]))
async def logic_game(client, message):
    cid = message.chat.id
    if cid not in games or not message.reply_to_message: return
    game = games[cid]
    if message.from_user.id != game["players"][game["turn"]]: return
    
    if message.text.strip().lower() == game["jawaban"][game["turn"]].lower():
        game["turn"] += 1
        if game["turn"] >= len(game["jawaban"]):
            for p in game["players"]: db_execute("UPDATE users SET points = points + 10 WHERE user_id = ?", (p,), commit=True)
            await message.reply("✅ Kompak! +10 Poin. Lanjut soal berikutnya..."); await asyncio.sleep(2)
            qs = get_new_question(cid, len(game["players"]))
            if not qs: await message.reply("🏁 Habis!"); del games[cid]; return
            q = random.choice(qs)
            game.update({"soal": q[1], "jawaban": q[2].split(","), "turn": 0})
            nxt = await client.get_users(game["players"][0])
            await message.reply(f"Next ❓: {q[1]}\n👉: {nxt.mention}")
        else:
            nxt = await client.get_users(game["players"][game["turn"]])
            await message.reply(f"✅ Benar! Giliran {nxt.mention}")
    else: await message.reply("❌ Salah!")

@app.on_message(filters.command("stop") & filters.group)
async def stop(client, message):
    m = await client.get_chat_member(message.chat.id, message.from_user.id)
    if m.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER] or message.from_user.id == OWNER_ID:
        if message.chat.id in games: del games[message.chat.id]; await message.reply("🛑 Stop!")

@app.on_message(filters.command("top"))
async def tops(client, message):
    u = db_execute("SELECT user_id, username, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT 10")
    t = "🏆 **LEADERBOARD**\n\n" + "\n".join([f"{i+1}. @{x[1] if x[1] else x[0]} - {x[2]} pts" for i, x in enumerate(u)])
    await message.reply(t)

@app.on_message(filters.command("help"))
async def help(client, message):
    await message.reply("📖 **CARA MAIN**\n1. `/mulai`\n2. Klik Gabung\n3. Jawab dengan **REPLY** bot!")

@app.on_message(filters.new_chat_members)
async def logs(client, message):
    if any(m.is_self for m in message.new_chat_members):
        db_execute("INSERT OR IGNORE INTO groups (chat_id, title) VALUES (?, ?)", (message.chat.id, message.chat.title), commit=True)
        await send_log(client, f"🏰 #NewGroup\nID: `{message.chat.id}`\nTitle: {message.chat.title}")

async def start_bot():
    await app.start()
    await app.set_bot_commands([BotCommand("start", "Status"), BotCommand("mulai", "Main"), BotCommand("top", "Skor"), BotCommand("help", "Bantuan")])
    print("🚀 Bot Ready!")
    await idle()

if __name__ == "__main__":
    init_db()
    app.run(start_bot())
