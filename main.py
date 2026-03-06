import os
import sqlite3
import json
import random
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
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("link_dev", "https://t.me/rian_eka")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("link_sup", "https://t.me/support")')
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("log_group", "0")')
    conn.commit()
    conn.close()

def seed_questions():
    check = db_query("SELECT COUNT(*) FROM questions", fetchone=True)[0]
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

def get_random_question(player_count):
    qs = db_query("SELECT soal, jawaban FROM questions WHERE word_count <= ?", (player_count,))
    return random.choice(qs) if qs else None

# --- GLOBAL VARIABLES ---
lobbies = {} 
games = {}   

# --- HANDLERS ---

@app.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Set Log Group", callback_data="set_log"), InlineKeyboardButton("Stats", callback_data="stats")],
        [InlineKeyboardButton("Backup DB (SendDB)", callback_data="send_db")],
        [InlineKeyboardButton("Update Links", callback_data="set_links")]
    ])
    await message.reply("🛠 **Admin Panel**", reply_markup=kb)

@app.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if data == "set_log":
        await callback_query.message.edit_text("Kirim ID grup log sekarang (Contoh: -100xxx)")
    elif data == "send_db":
        await callback_query.message.reply_document("bot_game.db")
    elif data == "join_lobby":
        if chat_id not in lobbies: return
        if user_id in lobbies[chat_id]["players"]: return await callback_query.answer("Lo udah join!")
        if len(lobbies[chat_id]["players"]) >= 3: return await callback_query.answer("Lobi penuh!")
        lobbies[chat_id]["players"].append(user_id)
        await callback_query.message.edit_text(f"🎮 **Lobi Terbuka!**\nPemain: {len(lobbies[chat_id]['players'])}/3", reply_markup=callback_query.message.reply_markup)
    
    elif data == "start_game":
        if chat_id not in lobbies: return
        if user_id != lobbies[chat_id]["host"]: return await callback_query.answer("Hanya Host!")
        p_list = lobbies[chat_id]["players"]
        if len(p_list) < 2: return await callback_query.answer("Minimal 2 orang!")
        
        q = get_random_question(len(p_list))
        if not q: return await callback_query.answer("Soal tidak ditemukan!")
        
        ans_list = q[1].split(",")
        games[chat_id] = {"soal": q[0], "jawaban": ans_list, "turn": 0, "players": p_list}
        
        p_info = await client.get_users(p_list[0])
        await callback_query.message.edit_text(f"🚀 **GAME DIMULAI!**\n\n❓ **SOAL:** {q[0]}\n👉 Giliran: {p_info.mention}\nJawab kata ke-1!")
        del lobbies[chat_id]

@app.on_message(filters.group & filters.text & ~filters.command(["mulai", "stop", "help", "top", "start", "admin"]))
async def check_answer(client, message):
    chat_id = message.chat.id
    if chat_id not in games: return
    game = games[chat_id]
    if message.from_user.id != game["players"][game["turn"]]: return
    
    if message.text.strip().lower() == game["jawaban"][game["turn"]].lower():
        game["turn"] += 1
        if game["turn"] >= len(game["jawaban"]):
            for p_id in game["players"]:
                db_query("UPDATE users SET points = points + 10 WHERE user_id = ?", (p_id,), commit=True)
            await message.reply("✅ **MENANG!** Semua dapet +10 poin! 🏆")
            del games[chat_id]
        else:
            p_info = await client.get_users(game["players"][game["turn"]])
            await message.reply(f"✅ Bener! Sekarang {p_info.mention} jawab kata ke-{game['turn']+1}!")

@app.on_message(filters.command("mulai") & filters.group)
async def start_lobby(client, message):
    chat_id = message.chat.id
    lobbies[chat_id] = {"host": message.from_user.id, "players": [message.from_user.id]}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Gabung ➕", callback_data="join_lobby")], [InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
    await message.reply(f"🎮 **Lobi Dibuka!**\nPemain: 1/3", reply_markup=kb)

@app.on_message(filters.command("start") & filters.private)
async def start_private(client, message):
    user = message.from_user
    db_query("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.username), commit=True)
    
    link_dev = db_query("SELECT value FROM settings WHERE key='link_dev'", fetchone=True)[0]
    link_sup = db_query("SELECT value FROM settings WHERE key='link_sup'", fetchone=True)[0]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Dev 👨‍💻", url=link_dev), InlineKeyboardButton("Support 👥", url=link_sup)],
        [InlineKeyboardButton("➕ Tambah ke Grup", url=f"https://t.me/{client.me.username}?startgroup=true")]
    ])
    
    await message.reply(
        f"Halo **{user.first_name}**! 👋\n\n"
        "Gue adalah Bot Tebak Kata Berantai. Cara mainnya harus kompak!\n\n"
        "Gunakan `/mulai` di grup untuk main.", 
        reply_markup=kb
    )

@app.on_message(filters.command("top"))
async def leaderboard(client, message):
    res = db_query("SELECT username, points FROM users ORDER BY points DESC LIMIT 10")
    if not res: return await message.reply("Belum ada pemain!")
    text = "🏆 **TOP 10 PEMAIN TERJAGO** 🏆\n\n"
    for i, (username, points) in enumerate(res, 1):
        un = f"@{username}" if username else f"User {i}"
        text += f"{i}. {un} — `{points} pts`\n"
    await message.reply(text)

# --- BOT STARTUP LOGIC ---
async def main():
    async with app:
        # Hapus dulu biar bersih
        await app.delete_bot_commands()
        
        # Menu Group (Semua Orang)
        await app.set_bot_commands([
            BotCommand("start", "Cek status"),
            BotCommand("mulai", "Buka lobi"),
            BotCommand("top", "Peringkat"),
            BotCommand("help", "Cara main")
        ], scope=BotCommandScopeAllGroupChats())

        # Menu Owner (Privat lo)
        await app.set_bot_commands([
            BotCommand("start", "Cek status"),
            BotCommand("admin", "Panel Owner"),
        ], scope=BotCommandScopeChat(OWNER_ID))
        
        print("✅ Bot Ready & Menu Updated!")
    
    await idle()

if __name__ == "__main__":
    init_db()
    seed_questions()
    app.run(main())
