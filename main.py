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
    c.execute('CREATE TABLE IF NOT EXISTS groups (chat_id INTEGER PRIMARY KEY, title TEXT)')
    
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

# --- HELPER FUNCTIONS ---
async def send_log(client, text):
    log_id_data = db_execute("SELECT value FROM settings WHERE key='log_group'", fetchone=True)
    if log_id_data and log_id_data[0] != "0":
        try:
            await client.send_message(int(log_id_data[0]), text)
        except: pass

### BARU: Fungsi ambil soal yang belum pernah dimainkan dalam sesi ini ###
def get_new_question(chat_id, word_count):
    game = games.get(chat_id)
    played_ids = game.get("history", []) if game else []
    
    placeholders = ','.join(['?'] * len(played_ids))
    query = f"SELECT id, soal, jawaban FROM questions WHERE word_count = ?"
    if played_ids:
        query += f" AND id NOT IN ({placeholders})"
    
    params = [word_count] + played_ids
    res = db_execute(query, tuple(params))
    
    if not res: # Jika soal habis, reset history
        if game: game["history"] = []
        return db_execute("SELECT id, soal, jawaban FROM questions WHERE word_count = ?", (word_count,), fetchone=False)
    
    return res

# --- HANDLERS ---

@app.on_message(filters.command("admin") & filters.user(OWNER_ID))
async def admin_panel(client, message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Soal", callback_data="admin_addsoal"), InlineKeyboardButton("📝 Set Start", callback_data="admin_setstart")],
        [InlineKeyboardButton("👤 Set Owner", callback_data="set_owner_link"), InlineKeyboardButton("👥 Set Support", callback_data="set_sup_link")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_bc"), InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("🆔 Set Log", callback_data="set_log"), InlineKeyboardButton("📁 Send DB", callback_data="send_db")],
        [InlineKeyboardButton("🔄 Reset Poin", callback_data="reset_all")]
    ])
    await message.reply("🛠 **SUPER ADMIN PANEL**", reply_markup=kb)

@app.on_message(filters.command("start") & filters.private)
async def start_private(client, message):
    user = message.from_user
    db_execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.username), commit=True)
    db_execute("UPDATE users SET username = ? WHERE user_id = ?", (user.username, user.id), commit=True)
    
    msg_data = db_execute("SELECT value FROM settings WHERE key='start_msg'", fetchone=True)
    msg = msg_data[0] if msg_data else "Halo!"
    
    link_dev = db_execute("SELECT value FROM settings WHERE key='link_dev'", fetchone=True)[0]
    link_sup = db_execute("SELECT value FROM settings WHERE key='link_sup'", fetchone=True)[0]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Dev 👨‍💻", url=link_dev), InlineKeyboardButton("Support 👥", url=link_sup)],
        [InlineKeyboardButton("➕ Tambah ke Grup", url=f"https://t.me/{client.me.username}?startgroup=true")],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="back_to_top")] ### BARU ###
    ])
    
    await message.reply(f"**{msg}**\n\nGunakan `/mulai` di grup untuk bermain.\n\nKlik tombol di bawah untuk cek skor global!", reply_markup=kb)

@app.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if data == "stats":
        u_count = db_execute("SELECT COUNT(*) FROM users", fetchone=True)[0]
        q_count = db_execute("SELECT COUNT(*) FROM questions", fetchone=True)[0]
        g_count = db_execute("SELECT COUNT(*) FROM groups", fetchone=True)[0]
        text = f"📊 **STATISTIK**\n👤 User: `{u_count}`\n🏰 Grup: `{g_count}`\n📝 Soal: `{q_count}`"
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="back_admin")]]))

    elif data.startswith("my_point_"):
        # Real-time update username sebelum cek poin
        db_execute("UPDATE users SET username = ? WHERE user_id = ?", (callback_query.from_user.username, user_id), commit=True)
        res = db_execute("SELECT points FROM users WHERE user_id = ?", (user_id,), fetchone=True)
        point = res[0] if res else 0
        rank = db_execute("SELECT COUNT(*) FROM users WHERE points > ?", (point,), fetchone=True)[0] + 1
        text = f"👤 **PROFIL POIN**\n\nID: `{user_id}`\nPoin: `{point}`\nRanking: `{rank}`"
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_top")]]))

    elif data == "back_to_top":
        users = db_execute("SELECT user_id, username, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT 10")
        text = "🏆 **LEADERBOARD POIN** 🏆\n\n"
        if not users: text += "Belum ada skor."
        for i, (uid, username, points) in enumerate(users, 1):
            mention = f"@{username}" if username else f"User {uid}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{medal} [{mention}](tg://user?id={uid}) — `{points} Poin`\n"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Cek Poin Saya", callback_data=f"my_point_{user_id}")]])
        await callback_query.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)

    elif data == "set_owner_link":
        await callback_query.message.edit_text("Ketik `/setdev URL_TELEGRAM` (Contoh: `/setdev https://t.me/rian_eka`)")
    
    elif data == "set_sup_link":
        await callback_query.message.edit_text("Ketik `/setsup URL_GRUP` (Contoh: `/setsup https://t.me/rian_eka_support`)")

    elif data == "join_lobby":
        if chat_id not in lobbies: return await callback_query.answer("Lobi ditutup!")
        if user_id in lobbies[chat_id]["players"]: return await callback_query.answer("Sudah gabung!")
        lobbies[chat_id]["players"].append(user_id)
        current = len(lobbies[chat_id]["players"])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Gabung ({current}/5)", callback_data="join_lobby")], [InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
        await callback_query.message.edit_text(f"🎮 **Lobi Terbuka!**\nPemain: {current}/5", reply_markup=kb)

    elif data == "start_game":
        if chat_id not in lobbies: return
        p_list = lobbies[chat_id]["players"]
        if len(p_list) < 2: return await callback_query.answer("Minimal 2 orang!", show_alert=True)
        
        qs_list = get_new_question(chat_id, len(p_list))
        if not qs_list: return await callback_query.answer("Soal untuk jumlah pemain ini tidak ditemukan!")
        
        q = random.choice(qs_list)
        games[chat_id] = {
            "soal": q[1], 
            "jawaban": q[2].split(","), 
            "turn": 0, 
            "players": p_list, 
            "history": [q[0]], # Catat ID soal agar tidak muncul lagi
            "salah_count": 0
        }
        del lobbies[chat_id]
        p_info = await client.get_users(p_list[0])
        await callback_query.message.edit_text(f"🚀 **GAME MULAI!**\n❓ Soal: {q[1]}\n👉 Giliran: {p_info.mention}\n(Kata ke-1)")

@app.on_message(filters.group & filters.text & ~filters.command(["mulai", "stop", "top", "start", "admin", "ganti", "gabung", "keluar"]))
async def check_answer(client, message):
    chat_id = message.chat.id
    if chat_id not in games: return
    
    game = games[chat_id]
    user_id = message.from_user.id
    if user_id != game["players"][game["turn"]]: return

    input_user = message.text.strip().lower()
    target_ans = game["jawaban"][game["turn"]].lower()

    if input_user == target_ans:
        game["turn"] += 1
        game["salah_count"] = 0 
        
        if game["turn"] >= len(game["jawaban"]):
            # MENANG SATU SOAL -> LANJUT OTOMATIS
            for pid in game["players"]:
                db_execute("UPDATE users SET points = points + 10 WHERE user_id = ?", (pid,), commit=True)
            
            await message.reply("✅ **KOMPAK!** Semua dapet +10 poin.\n⏳ Menyiapkan soal berikutnya...")
            await asyncio.sleep(2)
            
            # Cari soal baru
            qs_list = get_new_question(chat_id, len(game["players"]))
           if not qs_list:
               await message.reply("🏁 **SOAL HABIS!** Game selesai.")
               if chat_id in games: del games[chat_id]
               return
            
            q = random.choice(qs_list)
            game["soal"] = q[1]
            game["jawaban"] = q[2].split(",")
            game["turn"] = 0
            game["history"].append(q[0])
            
            p_next = await client.get_users(game["players"][0])
            await message.reply(f"Next ❓ Soal: {q[1]}\n👉 Giliran: {p_next.mention} (Kata ke-1)")
        else:
            p_next = await client.get_users(game["players"][game["turn"]])
            await message.reply(f"✅ Benar! Lanjut {p_next.mention} jawab kata ke-{game['turn']+1}")
    else:
        game["salah_count"] += 1
        if game["salah_count"] >= 3:
            kicked_user = game["players"].pop(game["turn"])
            await message.reply(f"❌ 3x Salah! {message.from_user.mention} dikick. Sisa pemain: {len(game['players'])}")
            if len(game["players"]) < 2:
                await message.reply("📉 Pemain kurang dari 2. Game bubar!")
                if chat_id in games: del games[chat_id]
                return
            if game["turn"] >= len(game["players"]): game["turn"] = 0
            p_next = await client.get_users(game["players"][game["turn"]])
            await message.reply(f"👉 Giliran dialihkan ke {p_next.mention}!")
            game["salah_count"] = 0
        else:
            await message.reply(f"❌ Salah! Kesempatan: {3 - game['salah_count']}x lagi.")

@app.on_message(filters.command("mulai") & filters.group)
async def start_lobby(client, message):
    if message.chat.id in games: return await message.reply("Game lagi jalan!")
    lobbies[message.chat.id] = {"host": message.from_user.id, "players": [message.from_user.id]}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Gabung ➕", callback_data="join_lobby")], [InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
    await message.reply("🎮 **LOBI TEBAK BERANTAI**\nKlik Gabung buat ikutan!", reply_markup=kb)

@app.on_message(filters.command("setdev") & filters.user(OWNER_ID))
async def set_dev_link(client, message):
    link = message.command[1]
    db_execute("UPDATE settings SET value = ? WHERE key = 'link_dev'", (link,), commit=True)
    await message.reply(f"✅ Link Owner diupdate ke: {link}")

@app.on_message(filters.command("setsup") & filters.user(OWNER_ID))
async def set_sup_link(client, message):
    link = message.command[1]
    db_execute("UPDATE settings SET value = ? WHERE key = 'link_sup'", (link,), commit=True)
    await message.reply(f"✅ Link Support diupdate ke: {link}")

@app.on_message(filters.command("top"))
async def leaderboard_cmd(client, message):
    # Update username sender biar selalu fresh di DB
    db_execute("UPDATE users SET username = ? WHERE user_id = ?", (message.from_user.username, message.from_user.id), commit=True)
    users = db_execute("SELECT user_id, username, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT 10")
    if not users: return await message.reply("Belum ada skor.")
    text = "🏆 **LEADERBOARD REAL-TIME** 🏆\n\n"
    for i, (uid, username, points) in enumerate(users, 1):
        mention = f"@{username}" if username else f"User {uid}"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} [{mention}](tg://user?id={uid}) — `{points} Poin`\n"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Cek Poin Saya", callback_data=f"my_point_{message.from_user.id}")]])
    await message.reply(text, reply_markup=kb, disable_web_page_preview=True)

# --- STARTUP ---
async def start_bot():
    await app.start()
    await app.set_bot_commands([
        BotCommand("start", "Cek Status"),
        BotCommand("help", "Cara Main"),
        BotCommand("mulai", "Mainkan Game"),
        BotCommand("top", "Leaderboard"),
        BotCommand("gabung", "Join Lobi"),
        BotCommand("keluar", "Keluar Game"),
        BotCommand("stop", "Hentikan Game")
    ], scope=BotCommandScopeAllGroupChats())
    print("🚀 Bot Ready!")
    await idle()

if __name__ == "__main__":
    init_db()
    app.run(start_bot())
