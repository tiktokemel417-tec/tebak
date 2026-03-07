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
    
    # Defaults
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
        [InlineKeyboardButton("➕ Add Soal", callback_data="admin_addsoal"), InlineKeyboardButton("📝 Set Start", callback_data="admin_setstart")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_bc"), InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("🆔 Set Log", callback_data="set_log"), InlineKeyboardButton("📁 Send DB", callback_data="send_db")],
        [InlineKeyboardButton("🔄 Reset Poin", callback_data="reset_all")]
    ])
    await message.reply("🛠 **SUPER ADMIN PANEL**", reply_markup=kb)
    
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
    
    # Ambil pesan start dari DB
    msg_data = db_execute("SELECT value FROM settings WHERE key='start_msg'", fetchone=True)
    msg = msg_data[0] if msg_data else "Halo!"
    
    # Ambil link dev & sup
    link_dev = db_execute("SELECT value FROM settings WHERE key='link_dev'", fetchone=True)[0]
    link_sup = db_execute("SELECT value FROM settings WHERE key='link_sup'", fetchone=True)[0]

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Dev 👨‍💻", url=link_dev), InlineKeyboardButton("Support 👥", url=link_sup)],
        [InlineKeyboardButton("➕ Tambah ke Grup", url=f"https://t.me/{client.me.username}?startgroup=true")]
    ])
    
    await send_log(client, f"👤 **User Start Bot**\n{user.mention} (`{user.id}`)")
    await message.reply(f"**{msg}**\n\nGunakan `/mulai` di grup untuk bermain.", reply_markup=kb)

@app.on_message(filters.command("setstart") & filters.user(OWNER_ID))
async def set_start_msg(client, message):
    try:
        new_msg = message.text.split(None, 1)[1]
        db_execute("UPDATE settings SET value = ? WHERE key = 'start_msg'", (new_msg,), commit=True)
        await message.reply("✅ Pesan /start berhasil diubah!")
    except:
        await message.reply("Contoh: `/setstart Halo selamat datang di bot tebak kata!`")

@app.on_callback_query()
async def handle_callbacks(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if data == "stats":
        u_count = db_execute("SELECT COUNT(*) FROM users", fetchone=True)[0]
        q_count = db_execute("SELECT COUNT(*) FROM questions", fetchone=True)[0]
        g_count = db_execute("SELECT COUNT(*) FROM groups", fetchone=True)[0] # Ambil dari tabel groups yang baru dibuat
        
        text = (
            "📊 **STATISTIK BOT**\n\n"
            f"👤 Total User: `{u_count}`\n"
            f"🏰 Total Grup: `{g_count}`\n"
            f"📝 Total Soal: `{q_count}`"
        )
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="back_admin")]]))

    # Taruh ini di dalam handle_callbacks (sejajar dengan elif data == "stats")
    elif data.startswith("my_point_"):
        target_id = int(data.split("_")[2])
        if user_id != target_id:
            return await callback_query.answer("Klik /top sendiri buat liat poin lu!", show_alert=True)
        
        # Ambil poin user dari DB
        res = db_execute("SELECT points FROM users WHERE user_id = ?", (user_id,), fetchone=True)
        point = res[0] if res else 0
        
        # Ambil ranking (hitung berapa orang yang poinnya lebih tinggi dari dia + 1)
        rank_res = db_execute("SELECT COUNT(*) FROM users WHERE points > ?", (point,), fetchone=True)
        rank = rank_res[0] + 1
        
        text = (
            "👤 **PROFIL POIN LU**\n\n"
            f"ID: `{user_id}`\n"
            f"Poin: `{point}`\n"
            f"Ranking: `{rank}`\n"
        )
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali ke Top 10", callback_data="back_to_top")]])
        await callback_query.message.edit_text(text, reply_markup=kb)

    elif data == "back_to_top":
        # Panggil ulang logic top 10
        users = db_execute("SELECT user_id, username, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT 10")
        text = "🏆 **LEADERBOARD POIN** 🏆\n\n"
        for i, (uid, username, points) in enumerate(users, 1):
            mention = f"@{username}" if username else f"User {uid}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            text += f"{medal} [{mention}](tg://user?id={uid}) — `{points} Poin`\n"
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📊 Cek Poin Saya", callback_data=f"my_point_{user_id}")]])
        await callback_query.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)

    elif data == "send_db":
        if user_id != OWNER_ID: 
            return await callback_query.answer("Hayo mau ngapain?", show_alert=True)
        await callback_query.message.reply_document("bot_game.db")
        await callback_query.answer("File Database dikirim!")

    elif data == "set_log":
        await callback_query.message.edit_text("Ketik `/setlog ID_GRUP` untuk menyetel log group.")

    elif data == "join_lobby":
        if chat_id not in lobbies: return await callback_query.answer("Lobi hangus!")
        if user_id in lobbies[chat_id]["players"]: return await callback_query.answer("Udah join!")
        lobbies[chat_id]["players"].append(user_id)
        current = len(lobbies[chat_id]["players"])
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Gabung ({current}/3)", callback_data="join_lobby")], [InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
        await callback_query.message.edit_text(f"🎮 **Lobi Terbuka!**\nPemain: {current}/3", reply_markup=kb)

    # Tambahkan ini di dalam handle_callbacks (di bawah elif data == "set_log")
    elif data == "admin_addsoal":
        await callback_query.message.edit_text("Gunakan format: `/addsoal Soal | Kata1,Kata2` di chat.")
        
    elif data == "admin_setstart":
        await callback_query.message.edit_text("Gunakan format: `/setstart Pesan lu` untuk ubah pesan start.")
        
    elif data == "admin_bc":
        await callback_query.message.edit_text("Gunakan format: `/bc Pesan lu` untuk kirim ke semua user.")

    elif data == "reset_all":
        # Konfirmasi reset poin
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("YA, RESET SEMUA", callback_data="confirm_reset")], [InlineKeyboardButton("BATAL", callback_data="stats")]])
        await callback_query.message.edit_text("⚠️ **YAKIN RESET SEMUA POIN USER?**", reply_markup=kb)

    elif data == "confirm_reset":
        db_execute("UPDATE users SET points = 0", commit=True)
        await callback_query.answer("🔥 SEMUA POIN TELAH DIRESET!", show_alert=True)
        await callback_query.message.edit_text("✅ Poin berhasil direset ke 0 untuk semua user.")

    elif data == "back_admin":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Add Soal", callback_data="admin_addsoal"), InlineKeyboardButton("📝 Set Start", callback_data="admin_setstart")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="admin_bc"), InlineKeyboardButton("📊 Stats", callback_data="stats")],
            [InlineKeyboardButton("🆔 Set Log", callback_data="set_log"), InlineKeyboardButton("📁 Send DB", callback_data="send_db")],
            [InlineKeyboardButton("🔄 Reset Poin", callback_data="reset_all")]
        ])
        await callback_query.message.edit_text("🛠 **SUPER ADMIN PANEL**", reply_markup=kb)

    elif data == "start_game":
        if chat_id not in lobbies: return
        p_list = lobbies[chat_id]["players"]
        if len(p_list) < 2: return await callback_query.answer("Minimal 2 orang!")
        
        qs = db_execute("SELECT soal, jawaban FROM questions WHERE word_count = ?", (len(p_list),))
        if not qs: return await callback_query.answer("Soal tdk ditemukan!")
        
        q = random.choice(qs)
        games[chat_id] = {"soal": q[0], "jawaban": q[1].split(","), "turn": 0, "players": p_list, "last_act": asyncio.get_event_loop().time()}
        del lobbies[chat_id]
        
        p_info = await client.get_users(p_list[0])
        await callback_query.message.edit_text(f"🚀 **GAME MULAI!**\n❓ Soal: {q[0]}\n👉 Giliran: {p_info.mention}")

        # Tambahan: Timer Otomatis Stop (5 Menit)
        await asyncio.sleep(300) 
        if chat_id in games:
            del games[chat_id]
            await client.send_message(chat_id, "⏰ **Waktu Habis!** Game dihentikan karena tidak ada aktivitas.")

@app.on_message(filters.group & filters.text & ~filters.command(["mulai", "stop", "top", "start", "admin", "ganti", "gabung", "keluar"]))
async def check_answer(client, message):
    chat_id = message.chat.id
    if chat_id not in games: return
    
    game = games[chat_id]
    user_id = message.from_user.id
    
    # Cek apakah sekarang giliran dia
    if user_id != game["players"][game["turn"]]: return

    input_user = message.text.strip().lower()
    target_ans = game["jawaban"][game["turn"]].lower()

    if input_user == target_ans:
        game["turn"] += 1
        game["salah_count"] = 0 # Reset hitungan salah
        
        if game["turn"] >= len(game["jawaban"]):
            # MENANG
            for pid in game["players"]:
                db_execute("UPDATE users SET points = points + 10 WHERE user_id = ?", (pid,), commit=True)
            await message.reply("✅ **KOMPAK!** Semua dapet +10 poin.")
            del games[chat_id]
        else:
            p_next = await client.get_users(game["players"][game["turn"]])
            await message.reply(f"✅ Benar! Lanjut {p_next.mention} jawab kata ke-{game['turn']+1}")
    else:
        # SALAH JAWAB
        game.setdefault("salah_count", 0)
        game["salah_count"] += 1
        
        if game["salah_count"] >= 3:
            # PROSES KICK DARI GAME
            kicked_user = game["players"].pop(game["turn"])
            await message.reply(f"❌ 3x Salah! {message.from_user.mention} dikick dari game. Sisa pemain: {len(game['players'])}")
            
            if len(game["players"]) < 2:
                await message.reply("📉 Pemain kurang dari 2. Game dihentikan!")
                del games[chat_id]
            else:
                # Geser turn ke orang berikutnya setelah kick
                if game["turn"] >= len(game["players"]): game["turn"] = 0
                p_next = await client.get_users(game["players"][game["turn"]])
                await message.reply(f"👉 Giliran dialihkan ke {p_next.mention}!")
                game["salah_count"] = 0
        else:
            await message.reply(f"❌ Salah! Kesempatan: {3 - game['salah_count']}x lagi.")
@app.on_message(filters.command("mulai") & filters.group)
async def start_lobby(client, message):
    db_execute("INSERT OR IGNORE INTO groups (chat_id, title) VALUES (?, ?)", (message.chat.id, message.chat.title), commit=True)
    lobbies[message.chat.id] = {"host": message.from_user.id, "players": [message.from_user.id]}
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Gabung ➕", callback_data="join_lobby")], [InlineKeyboardButton("Mulai ▶️", callback_data="start_game")]])
    await message.reply("🎮 **Lobi Dibuka!**", reply_markup=kb)

@app.on_message(filters.command("stop") & filters.group)
async def stop_game(client, message):
    chat_id = message.chat.id
    # Cek apakah pengirim adalah host atau admin (biar gak dirusuhin orang asing)
    if chat_id in games or chat_id in lobbies:
        del games[chat_id] if chat_id in games else lobbies.pop(chat_id)
        await message.reply("🛑 **Game/Lobi dihentikan paksa!**")
    else:
        await message.reply("Gak ada game yang lagi jalan, bos.")

@app.on_message(filters.command("gabung") & filters.group)
async def gabung_manual(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id not in lobbies:
        return await message.reply("❌ Gak ada lobi yang buka. Ketik `/mulai` dulu.")
    if user_id in lobbies[chat_id]["players"]:
        return await message.reply("Udah join, sabar nunggu host mulai ya!")
    
    lobbies[chat_id]["players"].append(user_id)
    await message.reply(f"✅ {message.from_user.mention} berhasil bergabung!")

@app.on_message(filters.command("keluar") & filters.group)
async def keluar_game(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id in games:
        if user_id in games[chat_id]["players"]:
            games[chat_id]["players"].remove(user_id)
            await message.reply(f"👋 {message.from_user.mention} keluar dari game.")
            if len(games[chat_id]["players"]) < 2:
                del games[chat_id]
                await message.reply("📉 Pemain kurang dari 2. Game bubar!")
    elif chat_id in lobbies:
        if user_id in lobbies[chat_id]["players"]:
            lobbies[chat_id]["players"].remove(user_id)
            await message.reply(f"👋 {message.from_user.mention} batal ikut.")

@app.on_message(filters.command("ganti") & filters.group)
async def ganti_soal(client, message):
    chat_id = message.chat.id
    if chat_id not in games: return
    game = games[chat_id]
    
    if game.get("used_ganti"):
        return await message.reply("⚠️ Fitur /ganti cuma bisa dipake sekali per game!")
    
    p_count = len(game["players"])
    qs = db_execute("SELECT soal, jawaban FROM questions WHERE word_count = ?", (p_count,))
    q = random.choice(qs)
    
    game["soal"] = q[0]
    game["jawaban"] = q[1].split(",")
    game["turn"] = 0
    game["used_ganti"] = True
    
    p_info = await client.get_users(game["players"][0])
    await message.reply(f"🔄 **SOAL DIGANTI!**\n❓ Soal: {q[0]}\n👉 Mulai lagi dari: {p_info.mention}")

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

@app.on_message(filters.command("bc") & filters.user(OWNER_ID))
async def broadcast(client, message):
    text = message.text.split(None, 1)[1]
    users = db_execute("SELECT user_id FROM users")
    count = 0
    for (uid,) in users:
        try:
            await client.send_message(uid, text)
            count += 1
        except: pass
    await message.reply(f"✅ Terkirim ke {count} user.")

@app.on_message(filters.command("setpoint") & filters.user(OWNER_ID))
async def set_point_admin(client, message):
    # Format: /setpoint @username 100
    cmd = message.command
    db_execute("UPDATE users SET points = ? WHERE username = ?", (cmd[2], cmd[1].replace("@","")), commit=True)
    await message.reply("✅ Poin berhasil diupdate.")

@app.on_message(filters.command("help"))
async def help_cmd(client, message):
    text = (
        "📖 **CARA BERMAIN**\n\n"
        "1. Tambahkan bot ke grup.\n"
        "2. Ketik `/mulai` untuk buka lobi.\n"
        "3. Minimal 2-3 orang harus `/gabung`.\n"
        "4. Host klik **Mulai**.\n"
        "5. Jawab kata demi kata sesuai urutan giliran!\n"
        "6. Salah 3x? Lu di-kick dari game!\n\n"
        "💡 Gunakan `/ganti` jika soal terlalu sulit (hanya 1x)."
    )
    await message.reply(text)

@app.on_message(filters.command("top"))
async def leaderboard(client, message):
    user_id = message.from_user.id
    # Ambil 10 besar + user_id buat link profil
    users = db_execute("SELECT user_id, username, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT 10")
    
    if not users:
        return await message.reply("Belum ada yang punya poin. Ayo main!")

    text = "🏆 **LEADERBOARD POIN** 🏆\n\n"
    for i, (uid, username, points) in enumerate(users, 1):
        # Format link profil (pake username kalo ada, kalo gak ada pake ID)
        mention = f"@{username}" if username else f"User {uid}"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        
        # Link profil: [Nama](tg://user?id=12345)
        text += f"{medal} [{mention}](tg://user?id={uid}) — `{points} Poin`\n"

    # Tombol Inline buat cek poin sendiri
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📊 Cek Poin Saya", callback_data=f"my_point_{user_id}")
    ]])

    await message.reply(text, reply_markup=kb, disable_web_page_preview=True)



# --- STARTUP ---
async def start_bot():
    await app.start()
    
    # Command User (Grup)
    await app.set_bot_commands([
        BotCommand("start", "Cek Status"),
        BotCommand("help", "Cara Main"),
        BotCommand("mulai", "Mainkan Game"),
        BotCommand("top", "Leaderboard"),
        BotCommand("gabung", "Join Lobi/Game"),
        BotCommand("keluar", "Keluar Game"),
        BotCommand("stop", "Hentikan Game"),
        BotCommand("ganti", "Ganti Soal (1x)")
    ], scope=BotCommandScopeAllGroupChats())

    # Command Admin (Private)
    await app.set_bot_commands([
        BotCommand("admin", "Panel Kontrol Admin"),
        BotCommand("start", "Restart Bot")
    ], scope=BotCommandScopeChat(OWNER_ID))
    
    print("🚀 Bot Tebak Berantai is Running!")
    await idle()

if __name__ == "__main__":
    init_db(); seed_questions()
    app.run(start_bot())
