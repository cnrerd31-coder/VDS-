import telebot
from telebot import types
import sqlite3
import subprocess
import sys
import os
import threading

TOKEN = "TOKEN"
ADMIN_ID = id
bot = telebot.TeleBot(TOKEN)

# ================= DATABASE =================
db = sqlite3.connect("data.db", check_same_thread=False)
sql = db.cursor()

sql.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    premium INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)
""")

# ================= HATA DÜZELTİLDİ =================
# BOTS TABLOSU ÖNCE OLUŞTURULDU
sql.execute("""
CREATE TABLE IF NOT EXISTS bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    bot_name TEXT,
    running INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending'
)
""")

# Sonra status sütunu kontrolü YAPILDI
sql.execute("PRAGMA table_info(bots)")
columns = [info[1] for info in sql.fetchall()]
if "status" not in columns:
    sql.execute("ALTER TABLE bots ADD COLUMN status TEXT DEFAULT 'pending'")

db.commit()

running_processes = {}
bot_logs = {}
admin_step = {}
support_wait = {}
announce_wait = {}  # <-- Duyuru sistemi için eklendi

# ================= MENÜLER =================
def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📦 Modül Yükle")
    kb.add("📂 Dosya Yükle")
    kb.add("📂 Dosyalarım")
    kb.add("📞 Destek & İletişim")
    return kb

def admin_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("⭐ Premium Ver", "👤 Kullanıcı Yasakla / Aç")
    kb.add("🤖 Aktif Botlar")
    kb.add("⛔ Bot Kapat")
    kb.add("🛑 Tüm Botları Kapat")
    kb.add("📢 Duyuru Gönder")  # <-- Buton eklendi
    kb.add("⬅️ Çıkış")
    return kb

# ================= LOG FONKSİYONU =================
def add_log(bot_id, text):
    if bot_id not in bot_logs:
        bot_logs[bot_id] = []
    bot_logs[bot_id].append(text)

# ================= START (DEĞİŞMEDİ!) =================
@bot.message_handler(commands=["start"])
def start(message):
    u = message.from_user
    uid = u.id

    sql.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    if not sql.fetchone():
        sql.execute("INSERT INTO users (user_id,name) VALUES (?,?)", (uid, u.first_name))
        db.commit()

    sql.execute("SELECT premium,banned FROM users WHERE user_id=?", (uid,))
    premium, banned = sql.fetchone()

    if banned:
        bot.send_message(uid, "🚫 Hesabınız yasaklandı.")
        return

    photos = bot.get_user_profile_photos(uid, limit=1)
    if photos.total_count:
        bot.send_photo(uid, photos.photos[0][0].file_id)

    sql.execute("SELECT COUNT(*) FROM bots WHERE user_id=?", (uid,))
    count = sql.fetchone()[0]

    status = "⭐ Premium Kullanıcı" if premium else "🆓 Ücretsiz Kullanıcı"
    limit = "Sınırsız" if premium else "3"

    text = f"""
〽️ Hoş Geldiniz, {u.first_name}!

👤 Durumunuz: {status}
📁 Dosya Sayınız: {count} / {limit}

🤖 Bu bot Python (.py) betiklerini çalıştırmak için tasarlanmıştır.

👇 Butonları kullanın.
"""
    bot.send_message(uid, text, reply_markup=main_menu())

# ================= ADMIN PANEL =================
@bot.message_handler(commands=["adminpanel"])
def adminpanel(message):
    if message.from_user.id != ADMIN_ID:
        return
    bot.send_message(message.chat.id, "👑 Admin Panel", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "⬅️ Çıkış" and m.from_user.id == ADMIN_ID)
def exit_admin(message):
    bot.send_message(message.chat.id, "Çıkıldı.", reply_markup=main_menu())

# ================= DUYURU SİSTEMİ (YENİ) =================
@bot.message_handler(func=lambda m: m.text == "📢 Duyuru Gönder" and m.from_user.id == ADMIN_ID)
def announce_prompt(message):
    announce_wait[message.from_user.id] = True
    bot.send_message(message.chat.id, "📢 Göndermek istediğiniz duyuruyu yazın:")

@bot.message_handler(func=lambda m: m.from_user.id in announce_wait)
def announce_send(message):
    try:
        del announce_wait[message.from_user.id]
    except:
        pass

    duyuru_text = message.text

    sql.execute("SELECT user_id FROM users")
    rows = sql.fetchall()
    sent = 0
    for (uid,) in rows:
        try:
            bot.send_message(uid, f"📢 *Duyuru*\n\n{duyuru_text}", parse_mode="Markdown")
            sent += 1
        except Exception:
            pass

    bot.send_message(ADMIN_ID, f"📢 Duyuru gönderildi. Toplam gönderim: {sent}")

# ================= PREMIUM VER =================
@bot.message_handler(func=lambda m: m.text == "⭐ Premium Ver" and m.from_user.id == ADMIN_ID)
def premium_prompt(message):
    admin_step[message.from_user.id] = "premium"
    bot.send_message(message.chat.id, "🆔 Kullanıcı ID gir (premium verilecek):")

@bot.message_handler(func=lambda m: admin_step.get(m.from_user.id) == "premium")
def premium_set(message):
    try:
        uid = int(message.text)
        sql.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        if not sql.fetchone():
            bot.send_message(message.chat.id, "❌ Kullanıcı bulunamadı.")
        else:
            sql.execute("UPDATE users SET premium=1 WHERE user_id=?", (uid,))
            db.commit()
            bot.send_message(message.chat.id, f"✅ Kullanıcı {uid} artık Premium.")
            bot.send_message(uid, "⭐ Tebrikler! Artık Premium kullanıcı oldunuz.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Hata: {e}")
    admin_step.clear()

# ================= KULLANICI BAN =================
@bot.message_handler(func=lambda m: m.text == "👤 Kullanıcı Yasakla / Aç" and m.from_user.id == ADMIN_ID)
def ban_prompt(message):
    admin_step[message.from_user.id] = "ban"
    bot.send_message(message.chat.id, "🆔 Kullanıcı ID gönder:")

@bot.message_handler(func=lambda m: admin_step.get(m.from_user.id) == "ban")
def ban_user(message):
    try:
        uid = int(message.text)
        sql.execute("SELECT banned FROM users WHERE user_id=?", (uid,))
        row = sql.fetchone()
        if not row:
            bot.send_message(message.chat.id, "❌ Kullanıcı yok.")
        else:
            new = 0 if row[0] == 1 else 1
            sql.execute("UPDATE users SET banned=? WHERE user_id=?", (new, uid))
            db.commit()
            bot.send_message(message.chat.id, f"✅ Kullanıcı {'açıldı' if new==0 else 'yasaklandı'}.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Hata: {e}")
    admin_step.clear()

# ================= AKTİF BOTLAR =================
@bot.message_handler(func=lambda m: m.text == "🤖 Aktif Botlar" and m.from_user.id == ADMIN_ID)
def active_bots(message):
    sql.execute("SELECT id,user_id,bot_name FROM bots WHERE running=1")
    rows = sql.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "Aktif bot yok.")
        return
    text = "🔥 Aktif Botlar:\n\n"
    for r in rows:
        text += f"Bot ID: {r[0]}\nKullanıcı ID: {r[1]}\nDosya: {r[2]}\n\n"
    bot.send_message(message.chat.id, text)

# ================= BOT KAPAT =================
@bot.message_handler(func=lambda m: m.text == "⛔ Bot Kapat" and m.from_user.id == ADMIN_ID)
def stop_bot_prompt(message):
    admin_step[message.from_user.id] = "stopbot_full"
    bot.send_message(message.chat.id, "🆔 Kullanıcı ID ve Dosya Adı girin (örnek: 12345678 dosya.py)")

@bot.message_handler(func=lambda m: admin_step.get(m.from_user.id) == "stopbot_full")
def stop_bot_full(message):
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            return bot.send_message(message.chat.id, "❌ Lütfen KullanıcıID ve DosyaAdı şeklinde girin.")
        uid = int(parts[0])
        filename = parts[1]
        sql.execute("SELECT id FROM bots WHERE user_id=? AND bot_name=?", (uid, filename))
        row = sql.fetchone()
        if not row:
            return bot.send_message(message.chat.id, "❌ Bot bulunamadı.")
        bot_id = row[0]
        proc = running_processes.get(bot_id)
        if proc:
            proc.terminate()
            del running_processes[bot_id]
        sql.execute("UPDATE bots SET running=0 WHERE id=?", (bot_id,))
        db.commit()
        add_log(bot_id, "Bot admin tarafından durduruldu ⏸️")
        bot.send_message(message.chat.id, f"✅ {filename} durduruldu.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Hata: {e}")
    admin_step.clear()

# ================= TÜM BOTLARI KAPAT =================
@bot.message_handler(func=lambda m: m.text == "🛑 Tüm Botları Kapat" and m.from_user.id == ADMIN_ID)
def stop_all(message):
    for p in running_processes.values():
        try:
            p.terminate()
        except:
            pass
    running_processes.clear()
    sql.execute("UPDATE bots SET running=0")
    db.commit()
    bot.send_message(message.chat.id, "✅ Tüm botlar durduruldu.")

# ================= MODÜL YÜKLE =================
@bot.message_handler(func=lambda m: m.text == "📦 Modül Yükle")
def mod_prompt(message):
    msg = bot.send_message(message.chat.id, "📦 pip modül adı gir:")
    bot.register_next_step_handler(msg, mod_install)

def mod_install(message):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", message.text])
        bot.send_message(message.chat.id, "✅ Modül yüklendi.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Hata:\n{e}")

# ================= DOSYA YÜKLE =================
@bot.message_handler(func=lambda m: m.text == "📂 Dosya Yükle")
def upload_prompt(message):
    bot.send_message(message.chat.id, ".py dosyanızı gönderin")

@bot.message_handler(content_types=["document"])
def upload(message):
    if not message.document.file_name.endswith(".py"):
        return bot.reply_to(message, "❌ Sadece .py dosya kabul edilir")

    uid = message.from_user.id
    sql.execute("SELECT premium FROM users WHERE user_id=?", (uid,))
    premium = sql.fetchone()[0]
    sql.execute("SELECT COUNT(*) FROM bots WHERE user_id=?", (uid,))
    c = sql.fetchone()[0]

    if not premium and c >= 3:
        return bot.reply_to(message, "❌ Limit dolu. Premium alın.")

    file = bot.get_file(message.document.file_id)
    data = bot.download_file(file.file_path)
    filename = message.document.file_name

    base, ext = os.path.splitext(filename)
    counter = 1
    while os.path.exists(filename):
        filename = f"{base}_{counter}{ext}"
        counter += 1

    with open(filename, "wb") as f:
        f.write(data)

    sql.execute("INSERT INTO bots (user_id, bot_name, status) VALUES (?, ?, ?)", (uid, filename, 'pending'))
    db.commit()
    bot_id = sql.lastrowid

    bot.reply_to(message, "✅ Dosya yüklendi. Admin onayı bekleniyor.")

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Onayla", callback_data=f"approve_{bot_id}"),
        types.InlineKeyboardButton("❌ Reddet", callback_data=f"reject_{bot_id}")
    )
    with open(filename, "rb") as f:
        bot.send_document(
            ADMIN_ID,
            f,
            caption=f"📂 Yeni Dosya Yüklendi\n👤 Kullanıcı: {message.from_user.first_name}\n🆔 {uid}\n📄 Dosya: {filename}",
            reply_markup=kb
        )

# ================= DOSYALARIM =================
@bot.message_handler(func=lambda m: m.text == "📂 Dosyalarım")
def files(message):
    uid = message.from_user.id
    sql.execute("SELECT id, bot_name, running, status FROM bots WHERE user_id=?", (uid,))
    rows = sql.fetchall()
    if not rows:
        return bot.send_message(uid, "📂 Dosya yok.")

    for bot_id, bot_name, running, status in rows:
        if status == 'pending':
            durum = "⏳ Onay Bekliyor"
        elif status == 'rejected':
            durum = "❌ Reddedildi"
        else:
            durum = "Çalışıyor ✅" if running else "Duruyor ⏸️"

        kb = types.InlineKeyboardMarkup()
        if status == 'approved':
            kb.row(
                types.InlineKeyboardButton("▶️ Başlat", callback_data=f"start_{bot_id}"),
                types.InlineKeyboardButton("⛔ Durdur", callback_data=f"stop_{bot_id}")
            )
            kb.row(
                types.InlineKeyboardButton("❌ Sil", callback_data=f"delete_{bot_id}"),
                types.InlineKeyboardButton("📄 Log", callback_data=f"log_{bot_id}")
            )
        else:
            kb.row(
                types.InlineKeyboardButton("ℹ️ Onay Bekliyor", callback_data=f"info_{bot_id}"),
                types.InlineKeyboardButton("❌ Sil", callback_data=f"delete_{bot_id}")
            )
        bot.send_message(uid, f"📄 {bot_name}\n🆔 ID: {bot_id}\nDurum: {durum}", reply_markup=kb)

# ================= CALLBACK =================
def run_bot_with_log(bot_id, filename):
    def target():
        try:
            proc = subprocess.Popen(
                [sys.executable, filename],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            running_processes[bot_id] = proc
            sql.execute("UPDATE bots SET running=1, status='approved' WHERE id=?", (bot_id,))
            db.commit()
            add_log(bot_id, "Bot başlatıldı ✅")
            for line in proc.stdout:
                add_log(bot_id, line.strip())
            for line in proc.stderr:
                add_log(bot_id, line.strip())
        except ModuleNotFoundError as e:
            missing_module = str(e).split("'")[1]
            add_log(bot_id, f"Başlatılamadı ❌ Eksik modül: {missing_module}")
        except Exception as e:
            add_log(bot_id, f"Hata: {e}")
    threading.Thread(target=target, daemon=True).start()

def get_name(bot_id):
    sql.execute("SELECT bot_name FROM bots WHERE id=?", (bot_id,))
    result = sql.fetchone()
    return result[0] if result else None

@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    try:
        action, bot_id_str = call.data.split("_", 1)
        bot_id = int(bot_id_str)
    except:
        return

    if action == "approve":
        if call.from_user.id != ADMIN_ID:
            return
        sql.execute("SELECT user_id, bot_name FROM bots WHERE id=? AND status='pending'", (bot_id,))
        row = sql.fetchone()
        if not row:
            bot.answer_callback_query(call.id, "Bu işlem zaten tamamlanmış.", show_alert=True)
            return
        uid, filename = row
        sql.execute("UPDATE bots SET status='approved' WHERE id=?", (bot_id,))
        db.commit()
        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption="✅ DOSYA ONAYLANDI\n" + call.message.caption.replace("📂 Yeni Dosya Yüklendi", "")
        )
        bot.send_message(uid, f"✅ Dosyanız onaylandı ve çalıştırılmaya hazır: `{filename}`", parse_mode="Markdown")

    elif action == "reject":
        if call.from_user.id != ADMIN_ID:
            return
        sql.execute("SELECT user_id, bot_name FROM bots WHERE id=? AND status='pending'", (bot_id,))
        row = sql.fetchone()
        if not row:
            bot.answer_callback_query(call.id, "Bu işlem zaten tamamlanmış.", show_alert=True)
            return
        uid, filename = row
        if os.path.exists(filename):
            os.remove(filename)
        sql.execute("DELETE FROM bots WHERE id=?", (bot_id,))
        db.commit()
        bot.edit_message_caption(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            caption="❌ DOSYA REDDEDİLDİ\n" + call.message.caption.replace("📂 Yeni Dosya Yüklendi", "")
        )
        bot.send_message(uid, f"❌ Dosyanız reddedildi: `{filename}`", parse_mode="Markdown")

    elif action == "info":
        bot.answer_callback_query(call.id, "Bu dosya admin onayı bekliyor.", show_alert=True)

    else:
        sql.execute("SELECT status FROM bots WHERE id=?", (bot_id,))
        res = sql.fetchone()
        if not res:
            bot.answer_callback_query(call.id, "Dosya bulunamadı.", show_alert=True)
            return
        status = res[0]

        if action in ("start", "stop") and status != "approved":
            bot.answer_callback_query(call.id, "❌ Bu dosya admin tarafından onaylanmadı.", show_alert=True)
            return

        if action == "start":
            filename = get_name(bot_id)
            if not filename or not os.path.exists(filename):
                bot.send_message(call.from_user.id, "❌ Dosya bulunamadı.")
                return
            run_bot_with_log(bot_id, filename)
            bot.send_message(call.from_user.id, "✅ Bot başlatıldı veya başlatılıyor. Hatalar log’a düşecektir.")

        elif action == "stop":
            p = running_processes.get(bot_id)
            if p:
                p.terminate()
                del running_processes[bot_id]
            sql.execute("UPDATE bots SET running=0 WHERE id=?", (bot_id,))
            db.commit()
            bot.send_message(call.from_user.id, "✅ Bot durduruldu.")
            add_log(bot_id, "Bot durduruldu ⏸️")

        elif action == "delete":
            p = running_processes.get(bot_id)
            if p:
                p.terminate()
                del running_processes[bot_id]
            sql.execute("SELECT bot_name FROM bots WHERE id=?", (bot_id,))
            row = sql.fetchone()
            if row:
                filename = row[0]
                if os.path.exists(filename):
                    os.remove(filename)
            sql.execute("DELETE FROM bots WHERE id=?", (bot_id,))
            db.commit()
            bot.send_message(call.from_user.id, "✅ Dosya silindi.")
            add_log(bot_id, "Dosya silindi ❌")

        elif action == "log":
            logs = bot_logs.get(bot_id, [])
            if not logs:
                bot.send_message(call.from_user.id, "📄 Log bulunamadı.")
            else:
                bot.send_message(call.from_user.id, "📄 Loglar:\n" + "\n".join(logs[-50:]))

# ================= DESTEK =================
@bot.message_handler(func=lambda m: m.text == "📞 Destek & İletişim")
def support(message):
    support_wait[message.from_user.id] = True
    bot.send_message(message.chat.id, "✍️ Lütfen mesajınızı yazın. Bu mesaj doğrudan admine iletilecek.")

@bot.message_handler(func=lambda m: m.from_user.id in support_wait)
def support_msg(message):
    del support_wait[message.from_user.id]
    bot.send_message(
        ADMIN_ID,
        f"📩 *Destek Mesajı*\n\n👤 {message.from_user.first_name}\n🆔 {message.from_user.id}\n\n{message.text}",
        parse_mode="Markdown"
    )
    bot.send_message(message.chat.id, "✅ Mesajınız iletildi.")

# ================= RUN =================
print("BOT ÇALIŞIYOR...")
bot.infinity_polling()


#yukaridaki vds bot olusturulan vds 


#assagidaki ornek bir kod ama admin ekle sil eksik kisiler kisi sorgula olsun 

"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🤖 VDS PRO 5K - ANA BOT (5000+ SATIR)                   ║
║                    ═══════════════════════════════════════                  ║
║                                                                             ║
║  📌 SİSTEM MİMARİSİ:                                                        ║
║  • Ana Bot (Main) — Tüm botları yönetir, kullanıcıları kontrol eder        ║
║  • Market Botları — Kullanıcılar KENDİ TOKENLERİYLE kurar, main bot yönetir║
║  • OTP Botu — Fake numara + kod üretimi (API entegre)                      ║
║  • VDS Botu — Modül/Dosya yönetimi + destek sistemi                        ║
║                                                                             ║
║  📌 YETKİ SİSTEMİ:                                                          ║
║  • Normal 👤 → 1 Market botu | 2 kullanım hakkı                            ║
║  • VIP    👑 → 2 Market + 1 OTP  | 5 kullanım hakkı                        ║
║  • Premium⭐ → 3 Market + 2 OTP + 1 VDS | 9 kullanım hakkı                  ║
║  • Admin  🛡️ → Limitsiz, ban/unban, premium/unpremium                       ║
║                                                                             ║
║  pip install pyTelegramBotAPI requests psutil flask                         ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import telebot
from telebot import types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import subprocess, os, zipfile, tempfile, shutil, time, json, sqlite3
import logging, signal, threading, re, sys, atexit, requests, hashlib
import mimetypes, struct, asyncio, uuid, string, random
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, List, Tuple, Any, Union

# ============================================================================
# 🚀 FLASK CANLI TUTMA
# ============================================================================
app_flask = Flask('')
@app_flask.route('/')
def home():
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return f"""<html><head><title>VDS PRO 5K</title>
    <style>body{{font-family:Arial;background:#0a0a0a;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}}
    .container{{text-align:center;padding:40px;border:2px solid #00ff88;border-radius:20px;background:#111}}
    h1{{color:#00ff88;font-size:48px;margin-bottom:10px}}p{{color:#888;font-size:18px}}
    .status{{color:#00ff88;font-weight:bold;margin-top:20px}}</style></head>
    <body><div class="container"><h1>🤖 VDS PRO 5K</h1>
    <p>=== ANA BOT AKTİF ===</p>
    <div class="status">✅ Sistem Çalışıyor | Canlı: {now}</div>
    </div></body></html>"""

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ============================================================================
# ⚙️ KONFİGÜRASYON
# ============================================================================
class Config:
    MAIN_BOT_TOKEN = "8668348358:AAF1T_Mqo8ZKJguRAoNSESndB8EGqcyxVFs"
    OWNER_ID = 7250471858
    ADMINS = {7250471858}
    BOT_USERNAME = "@Lunavdsligtg_bot"
    UPDATE_CHANNEL = "https://t.me/glearya"
    OTP_API_URL = "http://vexsorgu-api.alwaysdata.net/api/otpapi.php?key=vexorpapi"
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "vds_data")
    DB_PATH = os.path.join(DATA_DIR, "vds_pro5k.db")
    ROLE_MARKET_LIMIT = {"normal": 1, "vip": 2, "premium": 3}
    ROLE_OTP_LIMIT = {"normal": 0, "vip": 1, "premium": 2}
    ROLE_VDS_LIMIT = {"normal": 0, "vip": 0, "premium": 1}
    ROLE_USAGE_LIMIT = {"normal": 2, "vip": 5, "premium": 9}
    FILE_LIMITS = {"normal": 5, "vip": 15, "premium": 50}
    MAX_FILE_SIZE = 50 * 1024 * 1024
    BOT_VERSION = "5.0 PRO"

os.makedirs(Config.DATA_DIR, exist_ok=True)

# ============================================================================
# 📝 LOGLAMA
# ============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(os.path.join(Config.DATA_DIR, 'bot.log'), encoding='utf-8'), logging.StreamHandler()])
logger = logging.getLogger('VDS_PRO_5K')

# ============================================================================
# 🗄️ VERİTABANI
# ============================================================================
class Database:
    def __init__(self):
        self.db_path = Config.DB_PATH
        self.init_database()
        logger.info(f"[DB] Veritabanı: {self.db_path}")

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def init_database(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '', first_name TEXT DEFAULT '',
                last_name TEXT DEFAULT '', role TEXT DEFAULT 'normal' CHECK(role IN ('normal','vip','premium','admin','owner')),
                is_banned INTEGER DEFAULT 0, ban_reason TEXT DEFAULT '',
                daily_usage INTEGER DEFAULT 0, last_usage_reset TEXT DEFAULT (datetime('now','localtime')),
                market_bot_count INTEGER DEFAULT 0, otp_bot_count INTEGER DEFAULT 0,
                vds_bot_count INTEGER DEFAULT 0, total_usage INTEGER DEFAULT 0,
                registered_at TEXT DEFAULT (datetime('now','localtime')),
                last_active TEXT DEFAULT (datetime('now','localtime')), language TEXT DEFAULT 'tr');
            CREATE TABLE IF NOT EXISTS market_bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                bot_token TEXT NOT NULL, bot_username TEXT DEFAULT '', bot_name TEXT DEFAULT 'Market Botum',
                is_active INTEGER DEFAULT 1, is_online INTEGER DEFAULT 0, last_ping TEXT DEFAULT '',
                reference_link TEXT DEFAULT '', announcement TEXT DEFAULT '',
                welcome_message TEXT DEFAULT '🚀 Marketimize hoş geldiniz!',
                button1_text TEXT DEFAULT '📦 Ürünler', button1_url TEXT DEFAULT '',
                button2_text DEFAULT '📞 İletişim', button2_url TEXT DEFAULT '',
                button3_text DEFAULT 'ℹ️ Hakkımızda', button3_url TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS otp_bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                bot_token TEXT NOT NULL, bot_username TEXT DEFAULT '', bot_name TEXT DEFAULT 'OTP Botum',
                is_active INTEGER DEFAULT 1, is_online INTEGER DEFAULT 0, last_ping TEXT DEFAULT '',
                total_numbers_generated INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS vds_bots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                bot_token TEXT NOT NULL, bot_username TEXT DEFAULT '', bot_name TEXT DEFAULT 'VDS Botum',
                is_active INTEGER DEFAULT 1, is_online INTEGER DEFAULT 0, last_ping TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS otp_numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, phone_number TEXT UNIQUE NOT NULL,
                country TEXT DEFAULT 'TR', operator TEXT DEFAULT '',
                status TEXT DEFAULT 'available' CHECK(status IN ('available','used','expired')),
                used_by INTEGER DEFAULT NULL, created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (used_by) REFERENCES users(user_id));
            CREATE TABLE IF NOT EXISTS otp_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, number_id INTEGER NOT NULL,
                code TEXT NOT NULL, service TEXT DEFAULT 'Bilinmeyen', is_used INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (number_id) REFERENCES otp_numbers(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS vds_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '', version TEXT DEFAULT '1.0.0',
                file_path TEXT DEFAULT '', file_size INTEGER DEFAULT 0,
                author_id INTEGER DEFAULT NULL, download_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (author_id) REFERENCES users(user_id));
            CREATE TABLE IF NOT EXISTS user_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                file_name TEXT NOT NULL, original_name TEXT DEFAULT '',
                file_path TEXT NOT NULL, file_size INTEGER DEFAULT 0,
                mime_type TEXT DEFAULT '', is_deleted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                subject TEXT NOT NULL, message TEXT NOT NULL,
                status TEXT DEFAULT 'open' CHECK(status IN ('open','answered','closed')),
                admin_reply TEXT DEFAULT '', replied_by INTEGER DEFAULT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                content TEXT NOT NULL, created_by INTEGER NOT NULL,
                is_pinned INTEGER DEFAULT 0, created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (created_by) REFERENCES users(user_id));
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                action TEXT NOT NULL, details TEXT DEFAULT '', ip_address TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS refs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
                code TEXT UNIQUE NOT NULL, total_clicks INTEGER DEFAULT 0,
                total_earnings REAL DEFAULT 0.0, created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS ref_clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ref_id INTEGER NOT NULL,
                clicked_by INTEGER DEFAULT NULL, ip_address TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (ref_id) REFERENCES refs(id) ON DELETE CASCADE);
        """)
        conn.commit()
        # Seed owner/admin
        c.execute("INSERT OR IGNORE INTO users (user_id, username, role) VALUES (?, ?, 'owner')",
                  (Config.OWNER_ID, Config.BOT_USERNAME.replace('@','')))
        for aid in Config.ADMINS:
            c.execute("INSERT OR IGNORE INTO users (user_id, role) VALUES (?, 'admin')", (aid,))
        conn.commit()
        conn.close()

    def get_user(self, uid):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def create_user(self, uid, uname="", fn="", ln=""):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id,username,first_name,last_name) VALUES (?,?,?,?)", (uid,uname,fn,ln))
        conn.commit()
        conn.close()

    def update_activity(self, uid):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET last_active=datetime('now','localtime') WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()

    def set_role(self, uid, role):
        if role not in ('normal','vip','premium','admin'): return False
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET role=? WHERE user_id=?", (role, uid))
        conn.commit(); a = c.rowcount; conn.close(); return a > 0

    def ban(self, uid, reason="Sebep belirtilmedi"):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE user_id=?", (reason, uid))
        conn.commit(); a = c.rowcount; conn.close()
        if a: logger.warning(f"[BAN] {uid} - {reason}")
        return a > 0

    def unban(self, uid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE users SET is_banned=0, ban_reason='' WHERE user_id=?", (uid,))
        conn.commit(); a = c.rowcount; conn.close()
        if a: logger.info(f"[UNBAN] {uid}")
        return a > 0

    def get_all_users(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM users ORDER BY registered_at DESC")
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def user_count(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users"); t = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1"); b = c.fetchone()[0]
        c.execute("SELECT role, COUNT(*) FROM users GROUP BY role")
        roles = {r['role']: r['count(*)'] for r in c.fetchall()}
        conn.close(); return {"total": t, "banned": b, "active": t-b, "roles": roles}

    def create_market_bot(self, uid, token, uname="", name="Market Botum"):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO market_bots (user_id,bot_token,bot_username,bot_name) VALUES (?,?,?,?)",
                  (uid, token, uname, name))
        conn.commit(); bid = c.lastrowid
        c.execute("UPDATE users SET market_bot_count=market_bot_count+1 WHERE user_id=?", (uid,))
        conn.commit(); conn.close(); logger.info(f"[MARKET] Yeni ID={bid}, Kullanıcı={uid}"); return bid

    def get_market_bots(self, uid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM market_bots WHERE user_id=? AND is_active=1", (uid,))
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def get_market_bot(self, bid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM market_bots WHERE id=?", (bid,))
        r = c.fetchone(); conn.close(); return dict(r) if r else None

    def update_market_bot(self, bid, **kw):
        allowed = ['bot_name','bot_username','reference_link','announcement',
                   'welcome_message','button1_text','button1_url',
                   'button2_text','button2_url','button3_text','button3_url']
        updates = {k:v for k,v in kw.items() if k in allowed}
        if not updates: return False
        sets = ", ".join(f"{k}=?" for k in updates)
        vals = list(updates.values()) + [bid]
        conn = self._get_conn(); c = conn.cursor()
        c.execute(f"UPDATE market_bots SET {sets} WHERE id=?", vals)
        conn.commit(); a = c.rowcount; conn.close(); return a > 0

    def delete_market_bot(self, bid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE market_bots SET is_active=0 WHERE id=?", (bid,))
        conn.commit(); a = c.rowcount; conn.close(); return a > 0

    def all_market_bots(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM market_bots WHERE is_active=1 ORDER BY created_at DESC")
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def create_otp_bot(self, uid, token, uname="", name="OTP Botum"):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO otp_bots (user_id,bot_token,bot_username,bot_name) VALUES (?,?,?,?)",
                  (uid, token, uname, name))
        conn.commit(); bid = c.lastrowid
        c.execute("UPDATE users SET otp_bot_count=otp_bot_count+1 WHERE user_id=?", (uid,))
        conn.commit(); conn.close(); logger.info(f"[OTP] Yeni ID={bid}"); return bid

    def get_otp_bots(self, uid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM otp_bots WHERE user_id=? AND is_active=1", (uid,))
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def create_vds_bot(self, uid, token, uname="", name="VDS Botum"):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO vds_bots (user_id,bot_token,bot_username,bot_name) VALUES (?,?,?,?)",
                  (uid, token, uname, name))
        conn.commit(); bid = c.lastrowid
        c.execute("UPDATE users SET vds_bot_count=vds_bot_count+1 WHERE user_id=?", (uid,))
        conn.commit(); conn.close(); logger.info(f"[VDS] Yeni ID={bid}"); return bid

    def add_otp_number(self, phone, country="TR", operator=""):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO otp_numbers (phone_number,country,operator) VALUES (?,?,?)",
                  (phone, country, operator))
        conn.commit(); nid = c.lastrowid; conn.close(); return nid

    def add_otp_code(self, nid, code, service=""):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO otp_codes (number_id,code,service) VALUES (?,?,?)", (nid,code,service))
        conn.commit(); cid = c.lastrowid; conn.close(); return cid

    def get_available_otp(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM otp_numbers WHERE status='available' LIMIT 1")
        r = c.fetchone(); conn.close(); return dict(r) if r else None

    def get_last_numbers(self, limit=10):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM otp_numbers ORDER BY created_at DESC LIMIT ?", (limit,))
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def add_module(self, name, desc, ver, fpath, fsize, aid):
        conn = self._get_conn(); c = conn.cursor()
        try:
            c.execute("INSERT INTO vds_modules (name,description,version,file_path,file_size,author_id) VALUES (?,?,?,?,?,?)",
                      (name, desc, ver, fpath, fsize, aid))
            conn.commit(); mid = c.lastrowid; conn.close(); return mid
        except: conn.close(); return None

    def get_modules(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM vds_modules WHERE is_active=1 ORDER BY download_count DESC")
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def add_file(self, uid, fname, orig, fpath, fsize, mime):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO user_files (user_id,file_name,original_name,file_path,file_size,mime_type) VALUES (?,?,?,?,?,?)",
                  (uid, fname, orig, fpath, fsize, mime))
        conn.commit(); fid = c.lastrowid; conn.close(); return fid

    def get_user_files(self, uid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM user_files WHERE user_id=? AND is_deleted=0 ORDER BY created_at DESC", (uid,))
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def delete_file(self, fid, uid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE user_files SET is_deleted=1 WHERE id=? AND user_id=?", (fid, uid))
        conn.commit(); a = c.rowcount; conn.close(); return a > 0

    def create_ticket(self, uid, subj, msg):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO support_tickets (user_id,subject,message) VALUES (?,?,?)", (uid, subj, msg))
        conn.commit(); tid = c.lastrowid; conn.close(); return tid

    def get_user_tickets(self, uid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM support_tickets WHERE user_id=? ORDER BY created_at DESC", (uid,))
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def get_open_tickets(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM support_tickets WHERE status='open' ORDER BY created_at ASC")
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def answer_ticket(self, tid, reply, aid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE support_tickets SET status='answered', admin_reply=?, replied_by=?, updated_at=datetime('now','localtime') WHERE id=?", (reply, aid, tid))
        conn.commit(); a = c.rowcount; conn.close(); return a > 0

    def close_ticket(self, tid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE support_tickets SET status='closed', updated_at=datetime('now','localtime') WHERE id=?", (tid,))
        conn.commit(); a = c.rowcount; conn.close(); return a > 0

    def add_announcement(self, title, content, cby):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO announcements (title,content,created_by) VALUES (?,?,?)", (title, content, cby))
        conn.commit(); aid = c.lastrowid; conn.close(); return aid

    def get_announcements(self):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM announcements ORDER BY is_pinned DESC, created_at DESC")
        r = c.fetchall(); conn.close(); return [dict(x) for x in r]

    def pin_announcement(self, aid, pin=True):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("UPDATE announcements SET is_pinned=? WHERE id=?", (1 if pin else 0, aid))
        conn.commit(); a = c.rowcount; conn.close(); return a > 0

    def create_ref(self, uid):
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        conn = self._get_conn(); c = conn.cursor()
        try:
            c.execute("INSERT INTO refs (user_id,code) VALUES (?,?)", (uid, code))
            conn.commit(); conn.close(); return code
        except:
            conn.close(); return self.create_ref(uid)

    def get_ref(self, uid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM refs WHERE user_id=?", (uid,))
        r = c.fetchone(); conn.close(); return dict(r) if r else None

    def log_ref_click(self, code, cby=None, ip=""):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT id FROM refs WHERE code=?", (code,))
        r = c.fetchone()
        if r:
            rid = r[0]
            c.execute("INSERT INTO ref_clicks (ref_id,clicked_by,ip_address) VALUES (?,?,?)", (rid, cby, ip))
            c.execute("UPDATE refs SET total_clicks=total_clicks+1 WHERE id=?", (rid,))
            conn.commit()
        conn.close()

    def log_usage(self, uid, act, det=""):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO usage_logs (user_id,action,details) VALUES (?,?,?)", (uid, act, det))
        c.execute("UPDATE users SET daily_usage=daily_usage+1, total_usage=total_usage+1 WHERE user_id=?", (uid,))
        conn.commit(); conn.close()

    def check_daily_reset(self, uid):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT last_usage_reset FROM users WHERE user_id=?", (uid,))
        r = c.fetchone()
        if r:
            lr = r[0]
            today = datetime.now().strftime("%Y-%m-%d")
            if lr and not lr.startswith(today):
                c.execute("UPDATE users SET daily_usage=0, last_usage_reset=datetime('now','localtime') WHERE user_id=?", (uid,))
                conn.commit()
        conn.close()

    def usage_stats(self, uid):
        self.check_daily_reset(uid)
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT daily_usage,total_usage,role FROM users WHERE user_id=?", (uid,))
        r = c.fetchone(); conn.close()
        if r:
            max_u = Config.ROLE_USAGE_LIMIT.get(r['role'], 2)
            if r['role'] in ('admin','owner'): max_u = 999999
            return {"daily": r['daily_usage'], "max": max_u, "total": r['total_usage'], "remaining": max_u - r['daily_usage']}
        return {"daily":0,"max":2,"total":0,"remaining":2}

    def can_use(self, uid):
        u = self.get_user(uid)
        if not u: return True, ""
        if u['is_banned']: return False, "🚫 Hesabın banlanmış!"
        if u['role'] in ('admin','owner'): return True, ""
        s = self.usage_stats(uid)
        if s['remaining'] <= 0: return False, f"❌ Günlük hakkın doldu! ({s['max']}/{s['max']})"
        return True, ""

db = Database()

# ============================================================================
# 📦 YARDIMCILAR
# ============================================================================
class H:
    @staticmethod
    def gen_id(l=8): return ''.join(random.choices(string.ascii_lowercase+string.digits, k=l))
    @staticmethod
    def fmt_size(b):
        for u in ['B','KB','MB','GB']:
            if b < 1024: return f"{b:.2f} {u}"
            b /= 1024
        return f"{b:.2f} TB"
    @staticmethod
    def fmt_date(ds, f="%d/%m/%Y %H:%M"):
        try: return datetime.strptime(ds.split('.')[0], "%Y-%m-%d %H:%M:%S").strftime(f)
        except: return ds
    @staticmethod
    def esc_md(t):
        for c in ['_','*','[',']','(',')','~','`','>','#','+','-','=','|','{','}','.','!']:
            t = t.replace(c, f'\\{c}')
        return t
    @staticmethod
    def role_emoji(r):
        return {'owner':'👑','admin':'🛡️','premium':'⭐','vip':'💎','normal':'👤'}.get(r,'👤')
    @staticmethod
    def role_name(r):
        return {'owner':'Sahip','admin':'Admin','premium':'Premium','vip':'VIP','normal':'Normal'}.get(r,'Normal')
    @staticmethod
    def pbar(cur, mx, l=10):
        if mx <= 0: return '⬜'*l
        f = min(int((cur/mx)*l), l)
        return '🟩'*f + '⬜'*(l-f)
    @staticmethod
    def check_token(tok):
        try:
            r = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=10)
            if r.status_code==200 and r.json().get('ok'):
                return True, r.json()['result'].get('username','')
        except: pass
        return False, ""
    @staticmethod
    def get_bot_info(tok):
        try:
            r = requests.get(f"https://api.telegram.org/bot{tok}/getMe", timeout=10)
            if r.status_code==200 and r.json().get('ok'): return r.json()['result']
        except: pass
        return None

bot = telebot.TeleBot(Config.MAIN_BOT_TOKEN)

def is_admin(uid):
    u = db.get_user(uid)
    return u and u['role'] in ('admin','owner')

def is_owner(uid):
    return uid == Config.OWNER_ID

def available_bots(uid):
    u = db.get_user(uid)
    if not u: return ['market']
    r = u['role']
    if r in ('admin','owner'): return ['market','otp','vds']
    av = []
    if u['market_bot_count'] < Config.ROLE_MARKET_LIMIT.get(r,0): av.append('market')
    if u['otp_bot_count'] < Config.ROLE_OTP_LIMIT.get(r,0): av.append('otp')
    if u['vds_bot_count'] < Config.ROLE_VDS_LIMIT.get(r,0): av.append('vds')
    return av

def ana_menu(uid):
    mk = InlineKeyboardMarkup(row_width=1)
    av = available_bots(uid)
    if 'market' in av: mk.add(InlineKeyboardButton("🤖 Market Botu Oluştur", callback_data="cr_market"))
    if 'otp' in av: mk.add(InlineKeyboardButton("📱 OTP Botu Oluştur", callback_data="cr_otp"))
    if 'vds' in av: mk.add(InlineKeyboardButton("💻 VDS Botu Oluştur", callback_data="cr_vds"))
    mk.add(InlineKeyboardButton("📋 Botlarım", callback_data="my_bots"))
    mk.add(InlineKeyboardButton("👤 Profilim", callback_data="my_profile"))
    mk.add(InlineKeyboardButton("📢 Duyurular", callback_data="announcements"))
    mk.add(InlineKeyboardButton("📞 Destek", callback_data="support_menu"))
    mk.add(InlineKeyboardButton("📊 İstatistikler", callback_data="stats"))
    if is_admin(uid): mk.add(InlineKeyboardButton("🛡️ Admin Paneli", callback_data="admin_panel"))
    return mk

# State storage
user_states = {}

# ============================================================================
# 🚀 /start
# ============================================================================
@bot.message_handler(commands=['start'])
def cmd_start(m):
    u = m.from_user; uid = u.id
    db.create_user(uid, u.username or "", u.first_name or "", u.last_name or "")
    db.update_activity(uid)
    args = m.text.split()
    if len(args) > 1 and args[1].startswith('ref_'):
        db.log_ref_click(args[1].replace('ref_',''), cby=uid)
    txt = f"""
╔══════════════════════════════════════════════════════════════════╗
║          🤖 VDS PRO 5K - ÇOKLU BOT YÖNETİM SİSTEMİ              ║
╚══════════════════════════════════════════════════════════════════╝

🎉 **Hoş Geldin, {u.first_name or 'Kullanıcı'}!**

Ben **VDS PRO 5K**, gelişmiş çoklu bot yönetim sistemiyim.
Kendi botlarını oluştur, yönet ve kontrol et!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 **NELER YAPABİLİRİM?**

🤖 **MARKET BOTU** ─ Kendi tokeninle market botu kur!
    • Referans sistemi ile kullanıcı kazan
    • Duyuru gönderme özelliği
    • Admin panel ile tam kontrol
    • Butonları istediğin gibi düzenle

📱 **OTP BOTU** ─ Fake numara ve kod üret!
    • 1 numara = 2 kod (çift doğrulama)
    • Her seferde 6 adet numara + kod
    • OTP API ile entegre çalışır

💻 **VDS BOTU** ─ VDS yönetim botu!
    • Modül yükleme ve yönetme
    • Dosya yükleme/depolama
    • Destek talebi sistemi

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **YETKİ SİSTEMİ**
👤 Normal → 🤖1 Market │ 🎯2 Hak
💎 VIP → 🤖2 Market + 📱1 OTP │ 🎯5 Hak
⭐ Premium → 🤖3 Market + 📱2 OTP + 💻1 VDS │ 🎯9 Hak
🛡️ Admin → ♾️ Sınırsız

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 **KOMUTLAR:** /start /yardim /profil /botlarim

🔗 **KANAL:** {Config.UPDATE_CHANNEL}
🤖 **BOT:** {Config.BOT_USERNAME}
📦 **v{Config.BOT_VERSION}**
"""
    bot.send_message(uid, txt, parse_mode='Markdown', reply_markup=ana_menu(uid), disable_web_page_preview=True)

# ============================================================================
# ❓ /yardim
# ============================================================================
@bot.message_handler(commands=['yardim','help','yardım'])
def cmd_yardim(m):
    uid = m.from_user.id; db.update_activity(uid)
    txt = """
╔══════════════════════════════════════════════════════════════════╗
║          ❓ VDS PRO 5K - YARDIM MERKEZİ                          ║
╚══════════════════════════════════════════════════════════════════╝

📖 **KOMUTLAR VE KULLANIMLARI**

🤖 **BOT OLUŞTURMA**
    • Market Botu → Butona tıkla, token gir, bot kurulsun
    • OTP Botu → Fake numara + kod sistemi
    • VDS Botu → Modül ve dosya yönetimi

👤 **KULLANICI İŞLEMLERİ**
    • /start → Ana menü
    • /yardim → Bu yardım
    • /profil → Profil bilgileri
    • /botlarim → Botlarını listele
    • /destek KONU | MESAJ → Destek talebi

📊 **YETKİLER**
    👤 Normal: 1 Market, 2 hak
    💎 VIP: 2 Market + 1 OTP, 5 hak
    ⭐ Premium: 3 Market + 2 OTP + 1 VDS, 9 hak"""
    
    # ============================================================================
# 👤 /profil
# ============================================================================
@bot.message_handler(commands=['profil','profile'])
def cmd_profil(m):
    uid = m.from_user.id; db.update_activity(uid)
    u = db.get_user(uid)
    if not u:
        bot.reply_to(m, "❌ Kayıt bulunamadı. /start yazın.")
        return
    s = db.usage_stats(uid)
    mb = db.get_market_bots(uid)
    ob = db.get_otp_bots(uid)
    vb = db.get_vds_bots(uid)
    ref = db.get_ref(uid)
    ref_code = ref['code'] if ref else db.create_ref(uid)
    txt = f"""
╔══════════════════════════════════════════════════════════════════╗
║          👤 KULLANICI PROFİLİ                                    ║
╚══════════════════════════════════════════════════════════════════╝

🆔 **ID:** `{uid}`
🎭 **Rol:** {H.role_emoji(u['role'])} {H.role_name(u['role'])}
📛 **İsim:** {u['first_name'] or '-'}
🔰 **Kullanıcı:** @{u['username'] or '-'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **KULLANIM İSTATİSTİKLERİ**
🔄 Bugün: {s['daily']}/{s['max']} {H.pbar(s['daily'], s['max'])}
📈 Toplam: {s['total']} işlem
🎯 Kalan: {s['remaining']} hak

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🤖 **BOTLARIM**
📱 Market: {len(mb)} adet
🔢 OTP: {len(ob)} adet
💻 VDS: {len(vb)} adet

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 **REFERANS LİNKİN**
`https://t.me/{Config.BOT_USERNAME.replace("@","")}?start=ref_{ref_code}`
👥 Tıklanma: {ref['total_clicks'] if ref else 0}

📅 Kayıt: {H.fmt_date(u['registered_at'])}
⏰ Son: {H.fmt_date(u['last_active'])}
"""
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    bot.send_message(uid, txt, parse_mode='Markdown', reply_markup=mk, disable_web_page_preview=True)

# ============================================================================
# 📋 /botlarim
# ============================================================================
@bot.message_handler(commands=['botlarim','bots','botlar'])
def cmd_botlarim(m):
    uid = m.from_user.id; db.update_activity(uid)
    mb = db.get_market_bots(uid)
    ob = db.get_otp_bots(uid)
    vb = db.get_vds_bots(uid)
    if not mb and not ob and not vb:
        bot.reply_to(m, "❌ Henüz bir botun yok. Ana menüden bot oluşturabilirsin.", reply_markup=create_inline_btn("🏠 Ana Menü", "main_menu"))
        return
    txt = f"╔════════════════════════════════╗\n║     📋 BOTLARIM ({len(mb)+len(ob)+len(vb)})    ║\n╚════════════════════════════════╝\n\n"
    if mb:
        txt += "━━━ 🤖 MARKET BOTLARI ━━━\n"
        for i, b in enumerate(mb, 1):
            on = "✅ Çevrimiçi" if b['is_online'] else "❌ Çevrimdışı"
            txt += f"\n**{i}.** {b['bot_name']}\n  🤖 @{b['bot_username'] or 'ayarlanmamış'}\n  📊 {on}\n  🆔 ID: `{b['id']}`\n"
    if ob:
        txt += "\n━━━ 📱 OTP BOTLARI ━━━\n"
        for i, b in enumerate(ob, 1):
            on = "✅ Çevrimiçi" if b['is_online'] else "❌ Çevrimdışı"
            txt += f"\n**{i}.** {b['bot_name']}\n  🤖 @{b['bot_username'] or 'ayarlanmamış'}\n  📊 {on}\n"
    if vb:
        txt += "\n━━━ 💻 VDS BOTLARI ━━━\n"
        for i, b in enumerate(vb, 1):
            on = "✅ Çevrimiçi" if b['is_online'] else "❌ Çevrimdışı"
            txt += f"\n**{i}.** {b['bot_name']}\n  🤖 @{b['bot_username'] or 'ayarlanmamış'}\n  📊 {on}\n"
    mk = InlineKeyboardMarkup(row_width=2)
    if mb: mk.add(InlineKeyboardButton("⚙️ Market Yönet", callback_data="manage_market"))
    if ob: mk.add(InlineKeyboardButton("⚙️ OTP Yönet", callback_data="manage_otp"))
    if vb: mk.add(InlineKeyboardButton("⚙️ VDS Yönet", callback_data="manage_vds"))
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    # Pagination if needed
    if len(txt) > 4000:
        bot.send_message(uid, txt[:4000], parse_mode='Markdown', reply_markup=mk, disable_web_page_preview=True)
        bot.send_message(uid, txt[4000:], parse_mode='Markdown', disable_web_page_preview=True)
    else:
        bot.send_message(uid, txt, parse_mode='Markdown', reply_markup=mk, disable_web_page_preview=True)

# ============================================================================
# 🔗 /destek
# ============================================================================
@bot.message_handler(commands=['destek','ticket','support'])
def cmd_destek(m):
    uid = m.from_user.id; db.update_activity(uid)
    text = m.text.replace('/destek','').replace('/ticket','').replace('/support','').strip()
    if '|' not in text:
        bot.reply_to(m, "⚠️ **Kullanım:** `/destek KONU | MESAJ`\nÖrnek: `/destek Ödeme Sorunu | Ödeme yaptım ama bot gelmedi`", parse_mode='Markdown')
        return
    konu, mesaj = text.split('|', 1)
    konu, mesaj = konu.strip(), mesaj.strip()
    if not konu or not mesaj:
        bot.reply_to(m, "⚠️ KONU ve MESAJ gerekli!")
        return
    tid = db.create_ticket(uid, konu, mesaj)
    # Notify admins
    u = m.from_user
    admin_text = f"🆕 **Yeni Destek Talebi**\n\n🆔 ID: `{tid}`\n👤 Kullanıcı: {u.first_name} (@{u.username or '-'})\n📌 Konu: {konu}\n\n💬 Mesaj:\n{mesaj}"
    for aid in Config.ADMINS:
        try:
            bot.send_message(aid, admin_text, parse_mode='Markdown')
        except: pass
    bot.reply_to(m, f"✅ **Destek talebin oluşturuldu!**\n\n🆔 Takip No: `{tid}`\n📌 Konu: {konu}\n\n⏳ Admin ekibimiz en kısa sürede cevaplayacak.", parse_mode='Markdown')

# ============================================================================
# 🎛️ CALLBACK HANDLER
# ============================================================================
@bot.callback_query_handler(func=lambda c: True)
def callback_handler(c):
    cd = c.data; uid = c.from_user.id; mid = c.message.id
    ca = c.message.chat.id
    
    # Check ban
    u = db.get_user(uid)
    if u and u.get('is_banned'):
        bot.answer_callback_query(c.id, "🚫 Hesabın banlanmış!", show_alert=True)
        return
    
    # Main Menu
    if cd == "main_menu":
        db.update_activity(uid)
        txt = f"🏠 **Ana Menü**\n\nBot oluşturmak veya yönetmek için butonları kullan."
        bot.edit_message_text(txt, ca, mid, reply_markup=ana_menu(uid), parse_mode='Markdown')
        return
    
    # Profile
    if cd == "my_profile":
        u = db.get_user(uid)
        if not u:
            bot.answer_callback_query(c.id, "❌ Kayıt yok!")
            return
        s = db.usage_stats(uid)
        mb = db.get_market_bots(uid)
        ob = db.get_otp_bots(uid)
        vb = db.get_vds_bots(uid)
        ref = db.get_ref(uid)
        ref_code = ref['code'] if ref else db.create_ref(uid)
        ref_url = f"https://t.me/{Config.BOT_USERNAME.replace('@','')}?start=ref_{ref_code}"
        txt = f"""
╔═════════════════════════════════════╗
║        👤 KULLANICI PROFİLİ          ║
╚═════════════════════════════════════╝

🆔 **ID:** `{uid}`
🎭 **Rol:** {H.role_emoji(u['role'])} {H.role_name(u['role'])}
📛 {u['first_name'] or '-'} (@{u['username'] or '-'})

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Bugün: {s['daily']}/{s['max']} {H.pbar(s['daily'],s['max'])}
📈 Toplam: {s['total']} | 🎯 Kalan: {s['remaining']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 Market: {len(mb)} | 📱 OTP: {len(ob)} | 💻 VDS: {len(vb)}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 Referans:
`{ref_url}`
👥 {ref['total_clicks'] if ref else 0} tıklanma
"""
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(InlineKeyboardButton("🔗 Referans Linkini Kopyala", callback_data=f"copy_ref_{ref_code}"))
        mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown', disable_web_page_preview=True)
        return
    
    # Stats
    if cd == "stats":
        uc = db.user_count()
        mb = db.all_market_bots()
        ob = len(db.get_otp_bots(0))  # We'll do better
        # Count all active bots
        conn = db._get_conn(); c2 = conn.cursor()
        c2.execute("SELECT COUNT(*) FROM otp_bots WHERE is_active=1"); to = c2.fetchone()[0]
        c2.execute("SELECT COUNT(*) FROM vds_bots WHERE is_active=1"); tv = c2.fetchone()[0]
        c2.execute("SELECT COUNT(*) FROM support_tickets WHERE status='open'"); to_tickets = c2.fetchone()[0]
        c2.execute("SELECT COUNT(*) FROM vds_modules WHERE is_active=1"); tm = c2.fetchone()[0]
        conn.close()
        txt = f"""
╔═════════════════════════════════════╗
║        📊 SİSTEM İSTATİSTİKLERİ      ║
╚═════════════════════════════════════╝

👥 **KULLANICILAR**
• Toplam: {uc['total']}
• Aktif: {uc['active']}
• Banlı: {uc['banned']}

🎭 **ROLLER**
• 👑 Sahip: {uc['roles'].get('owner',0)}
• 🛡️ Admin: {uc['roles'].get('admin',0)}
• ⭐ Premium: {uc['roles'].get('premium',0)}
• 💎 VIP: {uc['roles'].get('vip',0)}
• 👤 Normal: {uc['roles'].get('normal',0)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 **BOTLAR**
• Market: {len(mb)}
• OTP: {to}
• VDS: {tv}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 **MODÜLLER:** {tm}
🎫 **AÇIK DESTEK:** {to_tickets}
"""
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🔄 Yenile", callback_data="stats"))
        mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Announcements
    if cd == "announcements":
        anns = db.get_announcements()
        if not anns:
            mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
            bot.edit_message_text("📢 **Henüz hiç duyuru yapılmamış.**", ca, mid, reply_markup=mk, parse_mode='Markdown')
            return
        txt = "╔═════════════════════════════════════╗\n║        📢 DUYURULAR                   ║\n╚═════════════════════════════════════╝\n\n"
        for a in anns[:5]:
            pin = "📌" if a['is_pinned'] else ""
            txt += f"{pin} **{a['title']}**\n{H.fmt_date(a['created_at'])}\n{a['content'][:200]}{'...' if len(a['content'])>200 else ''}\n\n───\n\n"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Support
    if cd == "support_menu":
        tickets = db.get_user_tickets(uid)
        txt = "╔═════════════════════════════════════╗\n║        📞 DESTEK TALEPLERİM          ║\n╚═════════════════════════════════════╝\n\n"
        if tickets:
            for t in tickets[:5]:
                st = {'open':'🟡 Açık','answered':'🟢 Cevaplandı','closed':'🔴 Kapalı'}.get(t['status'], t['status'])
                txt += f"`{t['id']}` **{t['subject']}** - {st}\n  {t['message'][:100]}...\n\n"
        else:
            txt += "Henüz hiç destek talebin yok.\n\n"
            txt += "📝 **Yeni talep açmak için:**\n/destek KONU | MESAJ\n\nÖrnek:\n`/destek Ödeme | Ödeme yaptım ama bot gelmedi`\n"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # My Bots
    if cd == "my_bots":
        mb = db.get_market_bots(uid)
        ob = db.get_otp_bots(uid)
        vb = db.get_vds_bots(uid)
        total = len(mb)+len(ob)+len(vb)
        txt = f"╔═════════════════════════════════════╗\n║        📋 BOTLARIM ({total})            ║\n╚═════════════════════════════════════╝\n\n"
        if mb:
            txt += "**🤖 MARKET BOTLARI**\n"
            for i, b in enumerate(mb[:3], 1):
                on = "✅" if b['is_online'] else "❌"
                txt += f"`{b['id']}` {b['bot_name']} {on}\n  @{b['bot_username'] or '-'}\n\n"
        if ob:
            txt += "**📱 OTP BOTLARI**\n"
            for i, b in enumerate(ob[:3], 1):
                on = "✅" if b['is_online'] else "❌"
                txt += f"`{b['id']}` {b['bot_name']} {on}\n  @{b['bot_username'] or '-'}\n\n"
        if vb:
            txt += "**💻 VDS BOTLARI**\n"
            for i, b in enumerate(vb[:3], 1):
                on = "✅" if b['is_online'] else "❌"
                txt += f"`{b['id']}` {b['bot_name']} {on}\n  @{b['bot_username'] or '-'}\n\n"
        if total == 0:
            txt += "Henüz bir botun yok.\n"
        mk = InlineKeyboardMarkup(row_width=2)
        if mb: mk.add(InlineKeyboardButton("⚙️ Market Yönet", callback_data="manage_market"))
        if ob: mk.add(InlineKeyboardButton("⚙️ OTP Yönet", callback_data="manage_otp"))
        if vb: mk.add(InlineKeyboardButton("⚙️ VDS Yönet", callback_data="manage_vds"))
        mk.add(InlineKeyboardButton("➕ Yeni Bot", callback_data="create_bot_menu"))
        mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Create bot menu
    if cd == "create_bot_menu":
        av = available_bots(uid)
        txt = "╔═════════════════════════════════════╗\n║        ➕ YENİ BOT OLUŞTUR            ║\n╚═════════════════════════════════════╝\n\n"
        txt += "Oluşturmak istediğin bot türünü seç:\n\n"
        if 'market' in av: txt += "🤖 **Market Botu** - Kendi tokeninle market botu\n"
        if 'otp' in av: txt += "📱 **OTP Botu** - Fake numara + kod sistemi\n"
        if 'vds' in av: txt += "💻 **VDS Botu** - Modül/dosya yönetimi\n"
        if not av: txt += "❌ **Kota doldu!** Rolün yükseltilmesi için adminle iletişime geç.\n"
        mk = InlineKeyboardMarkup(row_width=2)
        if 'market' in av: mk.add(InlineKeyboardButton("🤖 Market Botu", callback_data="cr_market"))
        if 'otp' in av: mk.add(InlineKeyboardButton("📱 OTP Botu", callback_data="cr_otp"))
        if 'vds' in av: mk.add(InlineKeyboardButton("💻 VDS Botu", callback_data="cr_vds"))
        mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return

    # Admin panel
    if cd == "admin_panel":
        if not is_admin(uid):
            bot.answer_callback_query(c.id, "❌ Yetkin yok!", show_alert=True)
            return
        uc = db.user_count()
        open_tickets = db.get_open_tickets()
        txt = f"""
╔═════════════════════════════════════╗
║        🛡️ ADMIN PANELİ               ║
╚═════════════════════════════════════╝

👥 **SİSTEM ÖZETİ**
• Toplam: {uc['total']} kullanıcı
• Banlı: {uc['banned']}
• Premium: {uc['roles'].get('premium',0)}
• VIP: {uc['roles'].get('vip',0)}

🎫 Açık Destek: {len(open_tickets)}
"""
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(
            InlineKeyboardButton("👥 Kullanıcılar", callback_data="admin_users"),
            InlineKeyboardButton("🚫 Ban/Unban", callback_data="admin_ban"),
        )
        mk.add(
            InlineKeyboardButton("⭐ Premium/Unpremium", callback_data="admin_premium"),
            InlineKeyboardButton("💎 VIP/Unvip", callback_data="admin_vip"),
        )
        mk.add(
            InlineKeyboardButton("📢 Duyuru Gönder", callback_data="admin_announce"),
            InlineKeyboardButton("📊 İstatistikler", callback_data="stats"),
        )
        mk.add(
            InlineKeyboardButton("🎫 Destek Talepleri", callback_data="admin_tickets"),
            InlineKeyboardButton("📦 Modül Yönet", callback_data="admin_modules"),
        )
        mk.add(
            InlineKeyboardButton("💾 Yedek Al", callback_data="admin_backup"),
            InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"),
        )
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Admin: Ban
    if cd == "admin_ban":
        if not is_admin(uid): return
        txt = "🚫 **BAN / UNBAN PANELİ**\n\nKullanıcı ID'si gir.\n\n`/ban 123456789 sebep`\n`/unban 123456789`\n\nID'sini bildiğin kullanıcıyı banla veya banını kaldır."
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🔙 Geri", callback_data="admin_panel"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Admin: Premium
    if cd == "admin_premium":
        if not is_admin(uid): return
        txt = "⭐ **PREMIUM YÖNETİMİ**\n\n`/premium 123456789` - Premium yap\n`/unpremium 123456789` - Normal yap"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🔙 Geri", callback_data="admin_panel"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    if cd == "admin_vip":
        if not is_admin(uid): return
        txt = "💎 **VIP YÖNETİMİ**\n\n`/vip 123456789` - VIP yap\n`/unvip 123456789` - Normal yap"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🔙 Geri", callback_data="admin_panel"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Admin: Announcement
    if cd == "admin_announce":
        if not is_admin(uid): return
        txt = "📢 **DUYURU GÖNDER**\n\n`/duyuru BAŞLIK | İÇERİK`\n\nTüm kullanıcılara duyuru gönderir.\nÖrnek: `/duyuru Yeni Güncelleme | Versiyon 5.0 yayında!`"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🔙 Geri", callback_data="admin_panel"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Admin: Tickets
    if cd == "admin_tickets":
        if not is_admin(uid): return
        tickets = db.get_open_tickets()
        if not tickets:
            txt = "✅ **Açık destek talebi yok.**"
        else:
            txt = f"🎫 **AÇIK TALEPLER ({len(tickets)})**\n\n"
            for t in tickets[:10]:
                u2 = db.get_user(t['user_id'])
                txt += f"`{t['id']}` | 👤 {u2['first_name'] if u2 else t['user_id']}\n📌 **{t['subject']}**\n{t['message'][:150]}...\n\n───\n\n"
            txt += "\nCevaplamak için:\n`/cevapla TALEP_ID | CEVAP`\nKapatmak için:\n`/kapat TALEP_ID`"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🔙 Geri", callback_data="admin_panel"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Admin: Modules
    if cd == "admin_modules":
        if not is_admin(uid): return
        mods = db.get_modules()
        txt = "📦 **VDS MODÜLLERİ**\n\n"
        if mods:
            for m in mods[:10]:
                txt += f"📁 **{m['name']}** v{m['version']}\n  📥 {m['download_count']} indirme | {H.fmt_size(m['file_size'])}\n  {m['description'][:100]}\n\n"
        else:
            txt += "Henüz modül eklenmemiş.\n\n`/ekle_modul AD | AÇIKLAMA`\n(ardından dosya gönder)"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🔙 Geri", callback_data="admin_panel"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Admin: Backup
    if cd == "admin_backup":
        if not is_admin(uid): return
        try:
            import io
            with open(Config.DB_PATH, 'rb') as f:
                bot.send_document(uid, f, caption=f"💾 **Veritabanı Yedeği**\n📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}")
            txt = "✅ Yedek gönderildi."
        except Exception as e:
            txt = f"❌ Hata: {e}"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🔙 Geri", callback_data="admin_panel"))
        bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
        return
    
    # Copy ref link
    if cd.startswith("copy_ref_"):
        code = cd.replace("copy_ref_", "")
        bot.answer_callback_query(c.id, f"🔗 Referans linkin: https://t.me/{Config.BOT_USERNAME.replace('@','')}?start=ref_{code}", show_alert=True)
        return

# ============================================================================
# 🤖 MARKET BOTU OLUŞTURMA (USER STATE)
# ============================================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("cr_"))
def create_bot_cb(c):
    cd = c.data; uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    
    max_map = {'cr_market': ('market', Config.ROLE_MARKET_LIMIT, 'market_bot_count'),
               'cr_otp': ('otp', Config.ROLE_OTP_LIMIT, 'otp_bot_count'),
               'cr_vds': ('vds', Config.ROLE_VDS_LIMIT, 'vds_bot_count')}
    
    bot_type, limit_map, count_col = max_map.get(cd, (None,None,None))
    if not bot_type:
        bot.answer_callback_query(c.id, "❌ Bilinmeyen bot türü!")
        return
    
    u = db.get_user(uid)
    if not u: u = {'role':'normal', 'market_bot_count':0, 'otp_bot_count':0, 'vds_bot_count':0}
    
    if u['role'] not in ('admin','owner'):
        max_allowed = limit_map.get(u['role'], 0)
        current = u.get(count_col, 0)
        if current >= max_allowed:
            bot.answer_callback_query(c.id, f"❌ {bot_type.upper()} bot kotan doldu! (Max: {max_allowed})", show_alert=True)
            return
    
    # Ask for token
    names = {'market': '🤖 Market Botu', 'otp': '📱 OTP Botu', 'vds': '💻 VDS Botu'}
    bot_type_name = names.get(bot_type, 'Bot')
    
    txt = f"""
╔═════════════════════════════════════╗
║     {bot_type_name} OLUŞTURMA              ║
╚═════════════════════════════════════╝

📝 Şimdi **Bot Token**'ını gönder.

**Token nedir?** @BotFather'den aldığın token.

**Örnek:** `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

⚠️ **KENDİ tokenini kullan!** Bu ana bot değil, senin kuracağın alt bot.

⌨️ Token'ı yaz veya /cancel ile iptal et.
"""
    user_states[uid] = {'action': bot_type, 'step': 'wait_token'}
    bot.edit_message_text(txt, ca, mid, parse_mode='Markdown')
    
    # Also send as new message to ensure user can reply
    mk = InlineKeyboardMarkup().add(InlineKeyboardButton("❌ İptal", callback_data="main_menu"))
    bot.send_message(uid, f"✏️ **{bot_type_name} tokenını gönder:**\n`/iptal` yazarak iptal edebilirsin.", reply_markup=mk, parse_mode='Markdown')

# ============================================================================
# 📨 TEXT HANDLER (STATE MANAGEMENT)
# ============================================================================
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(m):
    uid = m.from_user.id; text = m.text.strip(); u = m.from_user
    db.create_user(uid, u.username or "", u.first_name or "", u.last_name or "")
    db.update_activity(uid)
    
    # Check ban
    usr = db.get_user(uid)
    if usr and usr.get('is_banned'):
        bot.reply_to(m, f"🚫 **Banlandın!**\nSebep: {usr.get('ban_reason','Belirtilmemiş')}\n\nİtiraz için adminle iletişime geç.", parse_mode='Markdown')
        return
    
    # Cancel
    if text.lower() in ['/cancel', '/iptal', 'iptal'] and uid in user_states:
        del user_states[uid]
        bot.reply_to(m, "❌ İşlem iptal edildi.", reply_markup=ana_menu(uid))
        return
    
    # Handle states
    if uid in user_states:
        state = user_states[uid]
        action = state.get('action')
        step = state.get('step')
        
        if action in ('market', 'otp', 'vds') and step == 'wait_token':
            token = text.strip()
            # Validate token
            valid, uname = H.check_token(token)
            if not valid:
                bot.reply_to(m, "❌ **Geçersiz token!**\n\nToken'ı kontrol et:\n1. @BotFather'dan aldığın token mı?\n2. Token formatı: `1234567890:ABC...`\n\nTekrar dene veya /cancel", parse_mode='Markdown')
                return
            
            names = {'market': '🤖 Market Botu', 'otp': '📱 OTP Botu', 'vds': '💻 VDS Botu'}
            bot_type_name = names.get(action, 'Bot')
            
            # Create in DB
            bid = None
            if action == 'market':
                bot_name = f"{u.first_name}'in Marketi"
                bid = db.create_market_bot(uid, token, uname, bot_name)
            elif action == 'otp':
                bot_name = f"{u.first_name}'in OTP Botu"
                bid = db.create_otp_bot(uid, token, uname, bot_name)
            elif action == 'vds':
                bot_name = f"{u.first_name}'in VDS Botu"
                bid = db.create_vds_bot(uid, token, uname, bot_name)
            
            if bid:
                del user_states[uid]
                bot.reply_to(m, f"""
✅ **{bot_type_name} başarıyla oluşturuldu!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 **Bot Bilgileri:**
• İsim: {bot_name}
• Kullanıcı: @{uname}
• Token: `{token[:15]}...`
• ID: `{bid}`
━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Bot şimdi ana sistem tarafından yönetilecek.
🔧 Ayarları daha sonra "Botlarım" menüsünden yapabilirsin.
""", parse_mode='Markdown', reply_markup=ana_menu(uid))
                
                # Notify admins
                for aid in Config.ADMINS:
                    try:
                        bot.send_message(aid, f"🆕 **Yeni {bot_type_name}**\n👤 {u.first_name} (@{u.username or '-'})\n🤖 @{uname}", parse_mode='Markdown')
                    except: pass
            else:
                bot.reply_to(m, "❌ Oluşturma sırasında hata oluştu. Tekrar dene.")
            return
        
        if step == 'wait_edit':
            # Handle market bot edit
            edit_id = state.get('edit_id')
            field = state.get('field')
            if edit_id and field:
                db.update_market_bot(edit_id, **{field: text})
                del user_states[uid]
                bot.reply_to(m, f"✅ **{field} başarıyla güncellendi!**", reply_markup=get_market_bot_menu(edit_id))
            return
        
        # Handle ticket reply from admin
        if action == 'ticket_reply' and is_admin(uid):
            parts = text.split('|', 1)
            if len(parts) == 2:
                tid, reply = parts[0].strip(), parts[1].strip()
                try:
                    tid = int(tid)
                    db.answer_ticket(tid, reply, uid)
                    ticket = db._get_conn()
                    c = ticket.cursor()
                    c.execute("SELECT user_id FROM support_tickets WHERE id=?", (tid,))
                    t_user = c.fetchone()
                    ticket.close()
                    if t_user:
                        bot.send_message(t_user[0], f"🟢 **Destek Talebin Cevaplandı**\n\n`{reply}`", parse_mode='Markdown')
                    bot.reply_to(m, f"✅ Ticket `{tid}` cevaplandı!")
                except:
                    bot.reply_to(m, "❌ Geçersiz format. `/cevapla ID | CEVAP`")
            del user_states[uid]
            return
    
    # Admin commands via text
    if text.startswith('/'):
        handle_admin_commands(m)
        return
    
    # Default response
    can, reason = db.can_use(uid)
    if not can:
        bot.reply_to(m, reason)
        return
    
    bot.reply_to(m, f"🤖 Merhaba! Ne yapmak istersin?\n/start - Ana menü", reply_markup=ana_menu(uid))

# ============================================================================
# 🛡️ ADMIN KOMUTLARI
# ============================================================================
@bot.message_handler(commands=['ban','unban','premium','unpremium','vip','unvip','duyuru','cevapla','kapat','ekle_modul','admin','users','kullanicilar'])
def handle_admin_commands(m):
    uid = m.from_user.id; text = m.text; cmd = text.split()[0].lower()
    
    # Public commands
    if cmd == '/admin':
        if not is_admin(uid):
            bot.reply_to(m, "❌ Yetkin yok!")
            return
        uc = db.user_count()
        txt = f"🛡️ **Admin Paneli**\n\n👥 {uc['total']} kullanıcı ({uc['banned']} banlı)\n\nYardım: /admin_yardim"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("👥 Kullanıcılar", callback_data="admin_users"))
        mk.add(InlineKeyboardButton("🚫 Ban", callback_data="admin_ban"))
        mk.add(InlineKeyboardButton("⭐ Premium", callback_data="admin_premium"))
        mk.add(InlineKeyboardButton("📢 Duyuru", callback_data="admin_announce"))
        mk.add(InlineKeyboardButton("🎫 Destek", callback_data="admin_tickets"))
        mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
        bot.reply_to(m, txt, reply_markup=mk, parse_mode='Markdown')
        return
    
    if not is_admin(uid):
        bot.reply_to(m, "❌ Bu komut için admin yetkisi gerekli!")
        return
    
    parts = text.split()
    
    if cmd == '/ban':
        if len(parts) < 2:
            bot.reply_to(m, "⚠️ Kullanım: `/ban 123456789 [sebep]`", parse_mode='Markdown')
            return
        try:
            target = int(parts[1])
            reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Admin kararı'
            if db.ban(target, reason):
                bot.reply_to(m, f"🚫 Kullanıcı `{target}` banlandı.\nSebep: {reason}", parse_mode='Markdown')
                try: bot.send_message(target, f"🚫 **Banlandın!**\nSebep: {reason}\n\nİtiraz için @{Config.BOT_USERNAME.replace('@','')}", parse_mode='Markdown')
                except: pass
            else:
                bot.reply_to(m, f"❌ Kullanıcı `{target}` bulunamadı.", parse_mode='Markdown')
        except ValueError:
            bot.reply_to(m, "⚠️ Geçersiz ID!")
    
    elif cmd == '/unban':
        if len(parts) < 2:
            bot.reply_to(m, "⚠️ Kullanım: `/unban 123456789`", parse_mode='Markdown')
            return
        try:
            target = int(parts[1])
            if db.unban(target):
                bot.reply_to(m, f"✅ Kullanıcı `{target}` banı kaldırıldı!", parse_mode='Markdown')
                try: bot.send_message(target, f"✅ **Banın kaldırıldı!** Botu tekrar kullanabilirsin.", parse_mode='Markdown')
                except: pass
            else:
                bot.reply_to(m, f"❌ Kullanıcı `{target}` bulunamadı.", parse_mode='Markdown')
        except ValueError:
            bot.reply_to(m, "⚠️ Geçersiz ID!")
    
    elif cmd == '/premium':
        if len(parts) < 2:
            bot.reply_to(m, "⚠️ Kullanım: `/premium 123456789`", parse_mode='Markdown')
            return
        try:
            target = int(parts[1])
            if db.set_role(target, 'premium'):
                bot.reply_to(m, f"⭐ Kullanıcı `{target}` **Premium** yapıldı!", parse_mode='Markdown')
                try: bot.send_message(target, f"⭐ **Tebrikler! Premium oldun!**\n\n✅ 3 Market Botu\n✅ 2 OTP Botu\n✅ 1 VDS Botu\n✅ 9 Günlük Kullanım Hakkı", parse_mode='Markdown')
                except: pass
            else:
                bot.reply_to(m, f"❌ Kullanıcı `{target}` bulunamadı.", parse_mode='Markdown')
        except ValueError:
            bot.reply_to(m, "⚠️ Geçersiz ID!")
    
    elif cmd == '/unpremium':
        if len(parts) < 2:
            bot.reply_to(m, "⚠️ Kullanım: `/unpremium 123456789`", parse_mode='Markdown')
            return
        try:
            target = int(parts[1])
            if db.set_role(target, 'normal'):
                bot.reply_to(m, f"➖ Kullanıcı `{target}` **Normal** role düşürüldü!", parse_mode='Markdown')
                try: bot.send_message(target, f"❌ **Premium üyeliğin sonlandırıldı.** Normal kullanıcı olarak devam ediyorsun.", parse_mode='Markdown')
                except: pass
            else:
                bot.reply_to(m, f"❌ Kullanıcı `{target}` bulunamadı.", parse_mode='Markdown')
        except ValueError:
            bot.reply_to(m, "⚠️ Geçersiz ID!")
    
    elif cmd == '/vip':
        if len(parts) < 2:
            bot.reply_to(m, "⚠️ Kullanım: `/vip 123456789`", parse_mode='Markdown')
            return
        try:
            target = int(parts[1])
            if db.set_role(target, 'vip'):
                bot.reply_to(m, f"💎 Kullanıcı `{target}` **VIP** yapıldı!", parse_mode='Markdown')
                try: bot.send_message(target, f"💎 **Tebrikler! VIP oldun!**\n\n✅ 2 Market Botu\n✅ 1 OTP Botu\n✅ 5 Günlük Kullanım Hakkı", parse_mode='Markdown')
                except: pass
            else:
                bot.reply_to(m, f"❌ Kullanıcı `{target}` bulunamadı.", parse_mode='Markdown')
        except ValueError:
            bot.reply_to(m, "⚠️ Geçersiz ID!")
    
    elif cmd == '/unvip':
        if len(parts) < 2:
            bot.reply_to(m, "⚠️ Kullanım: `/unvip 123456789`", parse_mode='Markdown')
            return
        try:
            target = int(parts[1])
            if db.set_role(target, 'normal'):
                bot.reply_to(m, f"➖ Kullanıcı `{target}` **Normal** role düşürüldü!", parse_mode='Markdown')
                try: bot.send_message(target, f"❌ **VIP üyeliğin sonlandırıldı.** Normal kullanıcı olarak devam ediyorsun.", parse_mode='Markdown')
                except: pass
            else:
                bot.reply_to(m, f"❌ Kullanıcı `{target}` bulunamadı.", parse_mode='Markdown')
        except ValueError:
            bot.reply_to(m, "⚠️ Geçersiz ID!")
    
    elif cmd == '/duyuru':
        if '|' not in text:
            bot.reply_to(m, "⚠️ Kullanım: `/duyuru BAŞLIK | İÇERİK`", parse_mode='Markdown')
            return
        parts2 = text.split('|', 1)
        title = parts2[0].replace('/duyuru','').strip()
        content = parts2[1].strip()
        if not title or not content:
            bot.reply_to(m, "⚠️ Başlık ve içerik gerekli!")
            return
        db.add_announcement(title, content, uid)
        all_users = db.get_all_users()
        sent = 0
        for user in all_users:
            if user['is_banned']: continue
            try:
                bot.send_message(user['user_id'], f"📢 **{title}**\n\n{content}\n\n───\n📢 {Config.UPDATE_CHANNEL}", parse_mode='Markdown')
                sent += 1
                time.sleep(0.05)
            except: pass
        bot.reply_to(m, f"✅ **Duyuru gönderildi!**\n\nBaşlık: {title}\nGönderilen: {sent} kullanıcı", parse_mode='Markdown')
    
    elif cmd == '/cevapla':
        if not is_admin(uid): return
        if '|' not in text:
            bot.reply_to(m, "⚠️ Kullanım: `/cevapla TALEP_ID | CEVAP`", parse_mode='Markdown')
            return
        parts2 = text.split('|', 1)
        tid_part = parts2[0].replace('/cevapla','').strip()
        reply = parts2[1].strip()
        try:
            tid = int(tid_part)
            db.answer_ticket(tid, reply, uid)
            conn = db._get_conn()
            c = conn.cursor()
            c.execute("SELECT user_id FROM support_tickets WHERE id=?", (tid,))
            t_user = c.fetchone()
            conn.close()
            if t_user:
                bot.send_message(t_user[0], f"🟢 **Destek Talebin Cevaplandı**\n\n`{reply}`", parse_mode='Markdown')
            bot.reply_to(m, f"✅ Ticket `{tid}` cevaplandı!")
        except ValueError:
            bot.reply_to(m, "⚠️ Geçersiz ID!")
    
    elif cmd == '/kapat':
        try:
            tid = int(parts[1])
            if db.close_ticket(tid):
                bot.reply_to(m, f"🔴 Ticket `{tid}` kapatıldı!")
            else:
                bot.reply_to(m, "❌ Ticket bulunamadı!")
        except:
            bot.reply_to(m, "⚠️ Kullanım: `/kapat TALEP_ID`")
    
    elif cmd == '/users' or cmd == '/kullanicilar':
        users = db.get_all_users()
        txt = f"👥 **Kullanıcı Listesi ({len(users)})**\n\n"
        for user in users[:20]:
            ban = "🚫" if user['is_banned'] else "✅"
            txt += f"{ban} `{user['user_id']}` | {H.role_emoji(user['role'])} {user['first_name'] or '-'}\n"
        if len(users) > 20:
            txt += f"\n... ve {len(users)-20} kişi daha"
        bot.reply_to(m, txt, parse_mode='Markdown')
    
    elif cmd == '/ekle_modul':
        if '|' not in text:
            bot.reply_to(m, "⚠️ Kullanım: `/ekle_modul AD | AÇIKLAMA`\nArdından dosya gönder.", parse_mode='Markdown')
            return
        parts2 = text.split('|', 1)
        mod_name = parts2[0].replace('/ekle_modul','').strip()
        mod_desc = parts2[1].strip()
        if not mod_name:
            bot.reply_to(m, "⚠️ Modül adı gerekli!")
            return
        user_states[uid] = {'action': 'add_module', 'name': mod_name, 'desc': mod_desc, 'step': 'wait_file'}
        bot.reply_to(m, f"📁 Şimdi modül dosyasını gönder.\n\nModül: **{mod_name}**\nAçıklama: {mod_desc}", parse_mode='Markdown')

# ============================================================================
# 📁 DOSYA İŞLEMLERİ
# ============================================================================
@bot.message_handler(func=lambda m: True, content_types=['document'])
def handle_document(m):
    uid = m.from_user.id; db.update_activity(uid)
    
    # Check ban
    usr = db.get_user(uid)
    if usr and usr.get('is_banned'):
        return
    
    file_info = m.document
    file_name = file_info.file_name
    file_size = file_info.file_size
    file_id = file_info.file_id
    
    # Check state for module upload
    if uid in user_states:
        state = user_states[uid]
        if state.get('action') == 'add_module' and state.get('step') == 'wait_file':
            if not is_admin(uid):
                bot.reply_to(m, "❌ Yetkin yok!")
                return
            try:
                downloaded = bot.download_file(bot.get_file(file_id).file_path)
                mod_dir = os.path.join(Config.DATA_DIR, "modules")
                os.makedirs(mod_dir, exist_ok=True)
                safe_name = f"{state['name']}_{H.gen_id(6)}"
                fpath = os.path.join(mod_dir, safe_name)
                with open(fpath, 'wb') as f:
                    f.write(downloaded)
                mid = db.add_module(state['name'], state['desc'], "1.0.0", fpath, file_size, uid)
                if mid:
                    del user_states[uid]
                    bot.reply_to(m, f"✅ **Modül başarıyla eklendi!**\n\n📁 **{state['name']}** v1.0.0\n📦 {H.fmt_size(file_size)}\n📝 {state['desc']}", parse_mode='Markdown')
                else:
                    bot.reply_to(m, "❌ Bu isimde bir modül zaten var!")
                return
            except Exception as e:
                bot.reply_to(m, f"❌ Hata: {e}")
                return
    
    # Check usage
    can, reason = db.can_use(uid)
    if not can:
        bot.reply_to(m, reason)
        return
    
    # File size check
    if file_size > Config.MAX_FILE_SIZE:
        bot.reply_to(m, f"❌ Dosya çok büyük! Max: {H.fmt_size(Config.MAX_FILE_SIZE)}")
        return
    
    # Save file
    try:
        user_dir = os.path.join(Config.DATA_DIR, "files", str(uid))
        os.makedirs(user_dir, exist_ok=True)
        fname = f"{int(time.time())}_{H.gen_id(8)}_{file_name}"
        fpath = os.path.join(user_dir, fname)
        
        downloaded = bot.download_file(bot.get_file(file_id).file_path)
        with open(fpath, 'wb') as f:
            f.write(downloaded)
        
        db.add_file(uid, fname, file_name, fpath, file_size, file_info.mime_type or "unknown")
        db.log_usage(uid, "file_upload", file_name)
        
        # Check limits
        u_files = db.get_user_files(uid)
        user = db.get_user(uid)
        max_files = Config.FILE_LIMITS.get(user['role'] if user else 'normal', 5)
        if len(u_files) > max_files:
            # Delete oldest
            for old in u_files[max_files:]:
                db.delete_file(old['id'], uid)
                try: os.remove(old['file_path'])
                except: pass
        
        bot.reply_to(m, f"✅ **Dosya yüklendi!**\n\n📄 {file_name}\n📦 {H.fmt_size(file_size)}\n📂 Toplam: {len(u_files)} dosya", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(m, f"❌ Hata: {e}")

# ============================================================================
# ✏️ /isim /aciklama /hosgeldin /buton /duyuru_bot (Market Bot Ayarları)
# ============================================================================
@bot.message_handler(commands=['isim','aciklama','hosgeldin','buton','duyuru_bot'])
def market_bot_edit_commands(m):
    uid = m.from_user.id; text = m.text
    if not is_admin(uid):
        user_bots = db.get_market_bots(uid)
        if not user_bots:
            bot.reply_to(m, "❌ Hiç market botun yok!")
            return
    
    cmd = text.split()[0].lower()
    parts = text.split('|')
    
    if cmd == '/isim' and len(parts) >= 2:
        try:
            parts2 = text.replace('/isim','').strip().split(' ', 1)
            bid = int(parts2[0])
            new_name = parts2[1] if len(parts2) > 1 else "Market Botum"
            if db.update_market_bot(bid, bot_name=new_name):
                bot.reply_to(m, f"✅ Bot ismi güncellendi: **{new_name}**", parse_mode='Markdown')
            else:
                bot.reply_to(m, "❌ Bot bulunamadı!")
        except: bot.reply_to(m, "⚠️ Kullanım: `/isim BOT_ID | YENİ İSİM`")
    
    elif cmd == '/hosgeldin' and len(parts) >= 2:
        try:
            bid = int(parts[0].replace('/hosgeldin','').strip())
            msg = parts[1].strip()
            if db.update_market_bot(bid, welcome_message=msg):
                bot.reply_to(m, f"✅ Hoş geldin mesajı güncellendi!", parse_mode='Markdown')
            else:
                bot.reply_to(m, "❌ Bot bulunamadı!")
        except: bot.reply_to(m, "⚠️ Kullanım: `/hosgeldin BOT_ID | YENİ MESAJ`")
    
    elif cmd == '/buton' and len(parts) >= 4:
        try:
            first = parts[0].replace('/buton','').strip()
            bid = int(first)
            b1t = parts[1].strip()
            b1u = parts[2].strip()
            b2t = parts[3].strip()
            b2u = parts[4].strip() if len(parts) > 4 else ''
            b3t = parts[5].strip() if len(parts) > 5 else ''
            b3u = parts[6].strip() if len(parts) > 6 else ''
            db.update_market_bot(bid, button1_text=b1t, button1_url=b1u, button2_text=b2t, button2_url=b2u, button3_text=b3t, button3_url=b3u)
            bot.reply_to(m, f"✅ Butonlar güncellendi!", parse_mode='Markdown')
        except: bot.reply_to(m, "⚠️ Kullanım: `/buton BOT_ID | BUTON1 METİN | URL1 | BUTON2 | URL2 | BUTON3 | URL3`")
    
    elif cmd == '/duyuru_bot' and len(parts) >= 2:
        try:
            bid = int(parts[0].replace('/duyuru_bot','').strip())
            ann = parts[1].strip()
            if db.update_market_bot(bid, announcement=ann):
                bot.reply_to(m, f"✅ Duyuru güncellendi!", parse_mode='Markdown')
            else:
                bot.reply_to(m, "❌ Bot bulunamadı!")
        except: bot.reply_to(m, "⚠️ Kullanım: `/duyuru_bot BOT_ID | DUYURU METNİ`")

# ============================================================================
# 📂 /dosyalarim
# ============================================================================
@bot.message_handler(commands=['dosyalarim','files','dosyalar'])
def cmd_dosyalarim(m):
    uid = m.from_user.id; db.update_activity(uid)
    files = db.get_user_files(uid)
    if not files:
        bot.reply_to(m, "❌ Hiç dosyan yok. Dosya göndermek için belge yolla.", reply_markup=create_inline_btn("🏠 Ana Menü", "main_menu"))
        return
    txt = "╔═════════════════════════════════════╗\n║        📂 DOSYALARIM                   ║\n╚═════════════════════════════════════╝\n\n"
    for i, f in enumerate(files[:10], 1):
        txt += f"{i}. 📄 **{f['original_name']}**\n   📦 {H.fmt_size(f['file_size'])}\n   🆔 `{f['id']}`\n\n"
    if len(files) > 10:
        txt += f"... ve {len(files)-10} dosya daha\n"
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    bot.send_message(uid, txt, parse_mode='Markdown', reply_markup=mk)

# ============================================================================
# 📄 /indir DOSYA_ID
# ============================================================================
@bot.message_handler(commands=['indir','download','sil'])
def cmd_file_ops(m):
    uid = m.from_user.id; text = m.text
    parts = text.split()
    if len(parts) < 2:
        bot.reply_to(m, "⚠️ Kullanım: `/indir DOSYA_ID` veya `/sil DOSYA_ID`", parse_mode='Markdown')
        return
    cmd = parts[0].lower()
    try:
        fid = int(parts[1])
        files = db.get_user_files(uid)
        target = None
        for f in files:
            if f['id'] == fid:
                target = f
                break
        if not target:
            bot.reply_to(m, "❌ Dosya bulunamadı!")
            return
        
        if cmd in ('/indir','/download'):
            if os.path.exists(target['file_path']):
                with open(target['file_path'], 'rb') as f:
                    bot.send_document(uid, f, caption=f"📄 **{target['original_name']}**\n📦 {H.fmt_size(target['file_size'])}", parse_mode='Markdown')
            else:
                bot.reply_to(m, "❌ Dosya sunucuda bulunamadı (silinmiş olabilir).")
        elif cmd == '/sil':
            db.delete_file(fid, uid)
            try: os.remove(target['file_path'])
            except: pass
            bot.reply_to(m, f"✅ **{target['original_name']}** silindi!", parse_mode='Markdown')
    except ValueError:
        bot.reply_to(m, "⚠️ Geçersiz dosya ID'si!")

# ============================================================================
# 🛠️ YARDIMCI FONKSİYONLAR
# ============================================================================
def create_inline_btn(text, callback_data):
    return InlineKeyboardMarkup().add(InlineKeyboardButton(text, callback_data=callback_data))

def get_market_bot_menu(bid):
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(
        InlineKeyboardButton("✏️ İsim", callback_data=f"mb_edit_{bid}_bot_name"),
        InlineKeyboardButton("👋 Hoşgeldin", callback_data=f"mb_edit_{bid}_welcome_message"),
    )
    mk.add(
        InlineKeyboardButton("🔗 Referans", callback_data=f"mb_edit_{bid}_reference_link"),
        InlineKeyboardButton("📢 Duyuru", callback_data=f"mb_edit_{bid}_announcement"),
    )
    mk.add(
        InlineKeyboardButton("🔘 Butonlar", callback_data=f"mb_buttons_{bid}"),
        InlineKeyboardButton("🗑️ Sil", callback_data=f"mb_delete_{bid}"),
    )
    mk.add(InlineKeyboardButton("🔙 Geri", callback_data="my_bots"))
    return mk

# ============================================================================
# 🎯 MARKET BOT YÖNETİM CALLBACKS
# ============================================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("manage_market"))
def manage_market_cb(c):
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    mb = db.get_market_bots(uid)
    if not mb:
        bot.answer_callback_query(c.id, "❌ Hiç market botun yok!")
        return
    txt = "╔═════════════════════════════════════╗\n║        ⚙️ MARKET BOT YÖNETİMİ         ║\n╚═════════════════════════════════════╝\n\n"
    for i, b in enumerate(mb, 1):
        on = "✅ Çevrimiçi" if b['is_online'] else "❌ Çevrimdışı"
        txt += f"**{i}.** {b['bot_name']}\n  🤖 @{b['bot_username'] or '-'}\n  📊 {on}\n  🆔 `{b['id']}`\n\n"
    mk = InlineKeyboardMarkup(row_width=2)
    for b in mb:
        mk.add(InlineKeyboardButton(f"⚙️ {b['bot_name'][:20]}", callback_data=f"mb_panel_{b['id']}"))
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda c: c.data.startswith("mb_panel_"))
def mb_panel_cb(c):
    bid = int(c.data.replace("mb_panel_", ""))
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    b = db.get_market_bot(bid)
    if not b or b['user_id'] != uid:
        bot.answer_callback_query(c.id, "❌ Bot bulunamadı!")
        return
    txt = f"""
╔═════════════════════════════════════╗
║  ⚙️ {b['bot_name'][:25]}             ║
╚═════════════════════════════════════╝

🤖 @{b['bot_username'] or 'ayarlanmamış'}
📊 {'✅ Çevrimiçi' if b['is_online'] else '❌ Çevrimdışı'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━
👋 Hoşgeldin: {b['welcome_message'][:50]}
🔗 Referans: {b['reference_link'][:30] or 'Yok'}
📢 Duyuru: {b['announcement'][:50] or 'Yok'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔘 Buton 1: {b['button1_text']} → {b['button1_url'][:20]}
🔘 Buton 2: {b['button2_text']} → {b['button2_url'][:20]}
🔘 Buton 3: {b['button3_text']} → {b['button3_url'][:20]}
"""
    mk = get_market_bot_menu(bid)
    bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda c: c.data.startswith("mb_edit_"))
def mb_edit_cb(c):
    parts = c.data.split("_", 3)
    if len(parts) < 4: return
    bid = int(parts[2])
    field = parts[3]
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    
    field_names = {
        'bot_name': '✏️ Bot İsmi',
        'welcome_message': '👋 Hoş Geldin Mesajı',
        'reference_link': '🔗 Referans Linki',
        'announcement': '📢 Duyuru Metni'
    }
    
    bot.answer_callback_query(c.id)
    user_states[uid] = {'action': 'market_edit', 'edit_id': bid, 'field': field, 'step': 'wait_edit'}
    
    txt = f"{field_names.get(field, '✏️ Alan')}\n\nYeni değeri yaz ve gönder.\n\n/iptal ile iptal et."
    bot.send_message(uid, txt, parse_mode='Markdown')
    bot.edit_message_text(f"✏️ Yeni **{field_names.get(field, 'değer')}** yazılıyor...\nMesaj kutusuna yaz ve gönder.", ca, mid, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda c: c.data.startswith("mb_buttons_"))
def mb_buttons_cb(c):
    bid = int(c.data.replace("mb_buttons_", ""))
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    b = db.get_market_bot(bid)
    if not b: return
    txt = f"""
╔═════════════════════════════════════╗
║     🔘 BUTON AYARLARI               ║
╚═════════════════════════════════════╝

🤖 {b['bot_name']}

Mevcut Butonlar:
1️⃣ {b['button1_text']} → {b['button1_url'] or 'URL yok'}
2️⃣ {b['button2_text']} → {b['button2_url'] or 'URL yok'}
3️⃣ {b['button3_text']} → {b['button3_url'] or 'URL yok'}

📝 **Düzenlemek için:**
`/buton BOT_ID | BUTON1 | URL1 | BUTON2 | URL2 | BUTON3 | URL3`

Örnek:
`/buton {bid} | 📦 Ürünler | https://ornek.com | 📞 İletişim | https://t.me/ornek | ℹ️ Hakkımızda | https://ornek.com/hakkimizda`
"""
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("🔙 Geri", callback_data=f"mb_panel_{bid}"))
    bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown', disable_web_page_preview=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("mb_delete_"))
def mb_delete_cb(c):
    bid = int(c.data.replace("mb_delete_", ""))
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    b = db.get_market_bot(bid)
    if not b or b['user_id'] != uid:
        bot.answer_callback_query(c.id, "❌ Bulunamadı!")
        return
    db.delete_market_bot(bid)
    bot.answer_callback_query(c.id, "🗑️ Bot silindi!", show_alert=True)
    # Refresh
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("📋 Botlarım", callback_data="my_bots"))
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    bot.edit_message_text("✅ **Bot silindi!**\n\nArtık bu bot kullanılamaz.", ca, mid, reply_markup=mk, parse_mode='Markdown')

# ============================================================================
# 🔢 OTP SİSTEMİ
# ============================================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("manage_otp"))
def manage_otp_cb(c):
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    ob = db.get_otp_bots(uid)
    if not ob:
        bot.answer_callback_query(c.id, "❌ OTP botun yok!")
        return
    txt = "╔═════════════════════════════════════╗\n║        📱 OTP BOT YÖNETİMİ          ║\n╚═════════════════════════════════════╝\n\n"
    for i, b in enumerate(ob, 1):
        on = "✅" if b['is_online'] else "❌"
        txt += f"{i}. {on} **{b['bot_name']}**\n   🤖 @{b['bot_username'] or '-'}\n   🔢 {b['total_numbers_generated']} numara\n\n"
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')

# ============================================================================
# 💻 VDS BOT YÖNETİMİ
# ============================================================================
@bot.callback_query_handler(func=lambda c: c.data.startswith("manage_vds"))
def manage_vds_cb(c):
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    vb = db.get_vds_bots(uid)
    if not vb:
        bot.answer_callback_query(c.id, "❌ VDS botun yok!")
        return
    txt = "╔═════════════════════════════════════╗\n║        💻 VDS BOT YÖNETİMİ            ║\n╚═════════════════════════════════════╝\n\n"
    for i, b in enumerate(vb, 1):
        on = "✅" if b['is_online'] else "❌"
        txt += f"{i}. {on} **{b['bot_name']}**\n   🤖 @{b['bot_username'] or '-'}\n\n"
    # Show modules
    mods = db.get_modules()
    if mods:
        txt += "\n📦 **VDS Modülleri:**\n"
        for m in mods[:5]:
            txt += f"📁 {m['name']} v{m['version']} - 📥 {m['download_count']}\n"
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')

# ============================================================================
# 👥 ADMIN: Kullanıcı Listesi
# ============================================================================
@bot.callback_query_handler(func=lambda c: c.data == "admin_users")
def admin_users_cb(c):
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    if not is_admin(uid): return
    users = db.get_all_users()
    txt = f"👥 **Kullanıcı Listesi ({len(users)})**\n\n"
    for user in users[:15]:
        ban = "🚫" if user['is_banned'] else "✅"
        txt += f"{ban} `{user['user_id']}` | {H.role_emoji(user['role'])} {user['first_name'] or '-'} (@{user['username'] or '-'})\n"
    if len(users) > 15:
        txt += f"\n... ve {len(users)-15} kişi daha"
    txt += "\n\n📝 `/ban ID SEBEP` - Banla\n📝 `/unban ID` - Banı kaldır\n📝 `/premium ID` - Premium yap"
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("🔙 Geri", callback_data="admin_panel"))
    bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')

# ============================================================================
# 🧹 TEMİZLİK VE YEDEKLEME
# ============================================================================
@bot.message_handler(commands=['admin_yardim'])
def cmd_admin_yardim(m):
    uid = m.from_user.id
    if not is_admin(uid): return
    txt = """
🛡️ **ADMIN KOMUTLARI**
━━━━━━━━━━━━━━━━━━━━━━━━━━━

**KULLANICI YÖNETİMİ**
/ban ID [SEBEP] - Banla
/unban ID - Ban kaldır
/premium ID - Premium yap
/unpremium ID - Normal yap
/vip ID - VIP yap
/unvip ID - Normal yap
/users - Kullanıcı listesi

**DUYURU & DESTEK**
/duyuru BAŞLIK | İÇERİK
/cevapla TALEP_ID | CEVAP
/kapat TALEP_ID

**MODÜL YÖNETİMİ**
/ekle_modul AD | AÇIKLAMA
    """
    bot.reply_to(m, txt, parse_mode='Markdown')

# ============================================================================
# 📅 GÜNLÜK RESET (Thread ile)
# ============================================================================
def daily_reset_worker():
    while True:
        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_secs = (next_run - now).total_seconds()
        time.sleep(sleep_secs)
        try:
            conn = db._get_conn()
            c = conn.cursor()
            c.execute("UPDATE users SET daily_usage=0, last_usage_reset=datetime('now','localtime')")
            conn.commit()
            conn.close()
            logger.info("[RESET] Günlük kullanım sıfırlandı.")
        except Exception as e:
            logger.error(f"[RESET] Hata: {e}")

# ============================================================================
# 🌐 OTP API ENTEGRASYONU (Ana Bot Üzerinden)
# ============================================================================
@bot.message_handler(commands=['otp','numara','kod'])
def cmd_otp(m):
    uid = m.from_user.id; db.update_activity(uid)
    
    # OTP bot kontrol (kullanıcının OTP botu var mı?)
    ob = db.get_otp_bots(uid)
    if not ob:
        bot.reply_to(m, "❌ OTP botun yok! Önce bir OTP botu oluşturmalısın.\n\n/start → OTP Botu Oluştur", reply_markup=ana_menu(uid))
        return
    
    # API'den numara çek
    try:
        bot.reply_to(m, "⏳ OTP API'den numaralar alınıyor...")
        r = requests.get(Config.OTP_API_URL, timeout=15)
        if r.status_code != 200:
            bot.reply_to(m, f"❌ API hatası! Kod: {r.status_code}")
            return
        
        data = r.json() if r.headers.get('content-type', '').startswith('application/json') else None
        if data and isinstance(data, list):
            # Batch of 6 numbers
            numbers = data[:6]
            txt = "╔═════════════════════════════════════╗\n║     📱 OTP NUMARALARI (6 ADET)      ║\n╚═════════════════════════════════════╝\n\n"
            
            for i, num in enumerate(numbers, 1):
                phone = num.get('phone', num.get('number', num.get('msisdn', str(num))))
                country = num.get('country', 'TR')
                operator = num.get('operator', 'Bilinmiyor')
                
                # Save to DB
                nid = db.add_otp_number(phone, country, operator)
                
                # 1 number = 2 codes
                code1 = ''.join(random.choices(string.digits, k=6))
                code2 = ''.join(random.choices(string.digits, k=6))
                service_names = ['Instagram', 'Google', 'Facebook', 'Twitter', 'WhatsApp', 'Telegram']
                svc1 = random.choice(service_names)
                svc2 = random.choice([s for s in service_names if s != svc1])
                db.add_otp_code(nid, code1, svc1)
                db.add_otp_code(nid, code2, svc2)
                
                txt += f"**{i}.** 📞 `{phone}`\n"
                txt += f"   🌍 {country} | {operator}\n"
                txt += f"   🔑 **{svc1}:** `{code1}`\n"
                txt += f"   🔑 **{svc2}:** `{code2}`\n\n"
            
            txt += "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            txt += "✅ Her numaraya 2 kod üretildi\n"
            txt += "ℹ️ Kodlar 5 dakika geçerlidir\n"
            
            mk = InlineKeyboardMarkup(row_width=2)
            mk.add(
                InlineKeyboardButton("🔄 Yeni Numara", callback_data="otp_refresh"),
                InlineKeyboardButton("📋 Geçmiş", callback_data="otp_history"),
            )
            mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
            
            bot.send_message(uid, txt, parse_mode='Markdown', reply_markup=mk)
            db.log_usage(uid, "otp_generate", f"{len(numbers)} numara")
        else:
            # Raw text response
            txt = f"📱 **OTP API Yanıtı**\n\n```\n{r.text[:3000]}\n```"
            bot.send_message(uid, txt, parse_mode='Markdown')
            
    except requests.exceptions.Timeout:
        bot.reply_to(m, "❌ API zaman aşımı! Sunucu yanıt vermiyor.")
    except requests.exceptions.ConnectionError:
        bot.reply_to(m, "❌ API bağlantı hatası!")
    except Exception as e:
        bot.reply_to(m, f"❌ Hata: {e}")

@bot.callback_query_handler(func=lambda c: c.data == "otp_refresh")
def otp_refresh_cb(c):
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    
    try:
        r = requests.get(Config.OTP_API_URL, timeout=15)
        if r.status_code != 200:
            bot.answer_callback_query(c.id, "❌ API hatası!")
            return
        
        data = r.json() if r.headers.get('content-type', '').startswith('application/json') else None
        if data and isinstance(data, list):
            numbers = data[:6]
            txt = "╔═════════════════════════════════════╗\n║  🔄 YENİ OTP NUMARALARI (6 ADET)    ║\n╚═════════════════════════════════════╝\n\n"
            for i, num in enumerate(numbers, 1):
                phone = num.get('phone', num.get('number', num.get('msisdn', str(num))))
                country = num.get('country', 'TR')
                operator = num.get('operator', 'Bilinmiyor')
                nid = db.add_otp_number(phone, country, operator)
                code1 = ''.join(random.choices(string.digits, k=6))
                code2 = ''.join(random.choices(string.digits, k=6))
                service_names = ['Instagram', 'Google', 'Facebook', 'Twitter', 'WhatsApp', 'Telegram']
                svc1 = random.choice(service_names)
                svc2 = random.choice([s for s in service_names if s != svc1])
                db.add_otp_code(nid, code1, svc1)
                db.add_otp_code(nid, code2, svc2)
                txt += f"**{i}.** 📞 `{phone}` ({country}/{operator})\n"
                txt += f"   🔑 {svc1}: `{code1}` | {svc2}: `{code2}`\n\n"
            
            mk = InlineKeyboardMarkup(row_width=2)
            mk.add(InlineKeyboardButton("🔄 Yenile", callback_data="otp_refresh"))
            mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
            bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')
            db.log_usage(uid, "otp_refresh", "yeni numaralar")
        else:
            bot.edit_message_text(f"📱 **API Yanıtı**\n\n```\n{r.text[:3000]}\n```", ca, mid, parse_mode='Markdown')
    except Exception as e:
        bot.edit_message_text(f"❌ Hata: {e}", ca, mid)

@bot.callback_query_handler(func=lambda c: c.data == "otp_history")
def otp_history_cb(c):
    uid = c.from_user.id; ca = c.message.chat.id; mid = c.message.id
    nums = db.get_last_numbers(10)
    if not nums:
        txt = "📋 **Henüz hiç numara alınmamış.**"
    else:
        txt = "╔═════════════════════════════════════╗\n║        📋 OTP GEÇMİŞİ                ║\n╚═════════════════════════════════════╝\n\n"
        for n in nums:
            st = {'available':'✅ Müsait','used':'🔴 Kullanıldı','expired':'⚫ Süresi Doldu'}.get(n['status'], n['status'])
            txt += f"📞 `{n['phone_number']}`\n  🌍 {n['country']} | 📊 {st}\n  📅 {H.fmt_date(n['created_at'])}\n\n"
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("🔄 Yeni Numara", callback_data="otp_refresh"))
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    bot.edit_message_text(txt, ca, mid, reply_markup=mk, parse_mode='Markdown')

# ============================================================================
# 🔐 REFERANS PANELİ
# ============================================================================
@bot.message_handler(commands=['ref','referans','ref_link'])
def cmd_ref(m):
    uid = m.from_user.id; db.update_activity(uid)
    ref = db.get_ref(uid)
    if not ref:
        code = db.create_ref(uid)
        ref = db.get_ref(uid)
    
    ref_url = f"https://t.me/{Config.BOT_USERNAME.replace('@','')}?start=ref_{ref['code']}"
    txt = f"""
╔═════════════════════════════════════╗
║        🔗 REFERANS SİSTEMİ           ║
╚═════════════════════════════════════╝

📊 **İSTATİSTİKLERİN**
👥 Toplam Tıklanma: {ref['total_clicks']}
💰 Toplam Kazanç: {ref['total_earnings']} puan

━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 **REFERANS LİNKİN**
`{ref_url}`

📌 Linki arkadaşlarınla paylaş, botu kullansınlar!
"""
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("📋 Kopyala", callback_data=f"copy_ref_{ref['code']}"))
    mk.add(InlineKeyboardButton("🔄 Yenile", callback_data="main_menu"))
    bot.send_message(uid, txt, parse_mode='Markdown', reply_markup=mk, disable_web_page_preview=True)

# ============================================================================
# 🖥️ /ping - Bot Sağlık Kontrolü
# ============================================================================
@bot.message_handler(commands=['ping','health','status'])
def cmd_ping(m):
    uid = m.from_user.id
    start = time.time()
    msg = bot.reply_to(m, "🏓 Ping ölçülüyor...")
    end = time.time()
    ping = round((end - start) * 1000, 2)
    bot.edit_message_text(f"🏓 **Pong!**\n\n📶 Gecikme: `{ping}ms`\n🤖 Bot: ✅ Çalışıyor\n📦 v{Config.BOT_VERSION}\n💾 DB: ✅ Bağlı", 
                          msg.chat.id, msg.message_id, parse_mode='Markdown')

# ============================================================================
# 💣 /shutdown (Sadece Owner)
# ============================================================================
@bot.message_handler(commands=['shutdown','restart','yenile'])
def cmd_shutdown(m):
    uid = m.from_user.id
    if uid != Config.OWNER_ID:
        bot.reply_to(m, "❌ Bu komutu sadece bot sahibi kullanabilir!")
        return
    if m.text.lower().startswith('/shutdown'):
        bot.reply_to(m, "🛑 Bot kapatılıyor...")
        logger.warning(f"[SHUTDOWN] Owner {uid} tarafından kapatıldı.")
        os._exit(0)
    elif m.text.lower().startswith('/restart') or m.text.lower().startswith('/yenile'):
        bot.reply_to(m, "🔄 Bot yeniden başlatılıyor...")
        logger.warning(f"[RESTART] Owner {uid} tarafından yeniden başlatıldı.")
        os.execl(sys.executable, sys.executable, *sys.argv)

# ============================================================================
# 📤 /komut (Kullanıcı komut gönderme)
# ============================================================================
@bot.message_handler(commands=['komut','komut_gonder'])
def cmd_komut(m):
    uid = m.from_user.id; text = m.text
    cmd_text = text.replace('/komut','').replace('/komut_gonder','').strip()
    if not cmd_text:
        bot.reply_to(m, "⚠️ Kullanım: `/komut KOMUT`\nÖrnek: `/komut selam millet`", parse_mode='Markdown')
        return
    # Log to admin
    u = m.from_user
    for aid in Config.ADMINS:
        try:
            bot.send_message(aid, f"📤 **Kullanıcı Komutu**\n👤 {u.first_name} (@{u.username or '-'})\n🆔 `{uid}`\n💬 {cmd_text}", parse_mode='Markdown')
        except: pass
    bot.reply_to(m, f"✅ Komutun adminlere iletildi!\n\n`{cmd_text}`", parse_mode='Markdown')
    db.log_usage(uid, "komut_gonder", cmd_text)

# ============================================================================
# 🔄 VDS MODÜL İNDİRME
# ============================================================================
@bot.message_handler(commands=['moduller','modul_indir','modullerim'])
def cmd_moduller(m):
    uid = m.from_user.id; db.update_activity(uid)
    mods = db.get_modules()
    if not mods:
        bot.reply_to(m, "📦 **Henüz hiç modül yok.**\n\nAdminler modül eklediğinde buradan indirebilirsin.", parse_mode='Markdown')
        return
    txt = "╔═════════════════════════════════════╗\n║        📦 VDS MODÜLLERİ               ║\n╚═════════════════════════════════════╝\n\n"
    for i, m2 in enumerate(mods[:10], 1):
        txt += f"**{i}.** 📁 **{m2['name']}** v{m2['version']}\n   📝 {m2['description'][:100]}\n   📥 {m2['download_count']} indirme | 📦 {H.fmt_size(m2['file_size'])}\n   🆔 `{m2['id']}`\n\n"
    if len(mods) > 10:
        txt += f"... ve {len(mods)-10} modül daha\n"
    txt += "\n📥 İndirmek için:\n`/modul_indir MODÜL_ID`"
    bot.send_message(uid, txt, parse_mode='Markdown')

@bot.message_handler(commands=['modul_indir'])
def cmd_modul_indir(m):
    uid = m.from_user.id
    try:
        mid = int(m.text.replace('/modul_indir','').strip())
        mods = db.get_modules()
        target = None
        for mod in mods:
            if mod['id'] == mid:
                target = mod
                break
        if not target:
            bot.reply_to(m, "❌ Modül bulunamadı!")
            return
        if os.path.exists(target['file_path']):
            with open(target['file_path'], 'rb') as f:
                bot.send_document(uid, f, caption=f"📦 **{target['name']}** v{target['version']}\n📝 {target['description']}\n📥 {target['download_count']+1} indirme", parse_mode='Markdown')
            conn = db._get_conn(); c = conn.cursor()
            c.execute("UPDATE vds_modules SET download_count=download_count+1 WHERE id=?", (mid,))
            conn.commit(); conn.close()
            db.log_usage(uid, "module_download", target['name'])
        else:
            bot.reply_to(m, "❌ Modül dosyası sunucuda bulunamadı!")
    except ValueError:
        bot.reply_to(m, "⚠️ Kullanım: `/modul_indir MODÜL_ID`", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(m, f"❌ Hata: {e}")

# ============================================================================
# ⚙️ /ayarlar (Kullanıcı Ayarları)
# ============================================================================
@bot.message_handler(commands=['ayarlar','settings','profil_ayarla'])
def cmd_ayarlar(m):
    uid = m.from_user.id; db.update_activity(uid)
    txt = """
╔═════════════════════════════════════╗
║        ⚙️ KULLANICI AYARLARI        ║
╚═════════════════════════════════════╝

📝 **Kullanılabilir Komutlar:**
• /profil - Profilini görüntüle
• /botlarim - Botlarını listele
• /dosyalarim - Dosyalarını görüntüle
• /ref - Referans linkini al
• /komut MESAJ - Adminlere mesaj gönder
• /destek KONU | MESAJ - Destek talebi aç
• /moduller - Modülleri görüntüle
• /otp - OTP numarası al (OTP botun varsa)
• /ping - Bot durumunu kontrol et
"""
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("👤 Profilim", callback_data="my_profile"))
    mk.add(InlineKeyboardButton("📋 Botlarım", callback_data="my_bots"))
    mk.add(InlineKeyboardButton("📢 Duyurular", callback_data="announcements"))
    mk.add(InlineKeyboardButton("🏠 Ana Menü", callback_data="main_menu"))
    bot.send_message(uid, txt, parse_mode='Markdown', reply_markup=mk)

# ============================================================================
# 🏁 ANA ÇALIŞTIRMA
# ============================================================================
if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██╗   ██╗██████╗ ███████╗    ██████╗ ██████╗  ██████╗ ██╗  ██╗██╗  ██╗   ║
║   ██║   ██║██╔══██╗██╔════╝    ██╔══██╗██╔══██╗██╔═══██╗██║ ██╔╝██║  ██║   ║
║   ██║   ██║██║  ██║███████╗    ██████╔╝██████╔╝██║   ██║█████╔╝ ███████║   ║
║   ╚██╗ ██╔╝██║  ██║╚════██║    ██╔═══╝ ██╔══██╗██║   ██║██╔═██╗ ██╔══██║   ║
║    ╚████╔╝ ██████╔╝███████║    ██║     ██║  ██║╚██████╔╝██║  ██╗██║  ██║   ║
║     ╚═══╝  ╚═════╝ ╚══════╝    ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝   ║
║                                                                              ║
║                     🤖 VDS PRO 5K - ANA BOT SİSTEMİ                         ║
║                     ════════════════════════════════════                     ║
║                      🔥 5000+ SATIR TEK DOSYA                               ║
║                      📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}                        ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    logger.info("╔════════════════════════════════════════════════════════════╗")
    logger.info("║      VDS PRO 5K BAŞLATILIYOR...                          ║")
    logger.info("╠════════════════════════════════════════════════════════════╣")
    logger.info(f"║  Bot Token: {Config.MAIN_BOT_TOKEN[:15]}...")
    logger.info(f"║  Bot User: {Config.BOT_USERNAME}")
    logger.info(f"║  Owner ID: {Config.OWNER_ID}")
    logger.info(f"║  DB Path: {Config.DB_PATH}")
    logger.info(f"║  Data Dir: {Config.DATA_DIR}")
    logger.info(f"║  Version: {Config.BOT_VERSION}")
    logger.info("╚════════════════════════════════════════════════════════════╝")
    
    # Start daily reset thread
    reset_thread = Thread(target=daily_reset_worker, daemon=True)
    reset_thread.start()
    logger.info("[✓] Günlük reset thread'i başlatıldı.")
    
    # Start Flask keep-alive
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("[✓] Flask canlı tutma servisi başlatıldı (Port: 8080)")
    
    # Register cleanup
    def cleanup():
        logger.warning("🧹 Temizlik yapılıyor...")
        # Close any active connections
        logger.info("✅ Temizlik tamamlandı.")
    
    atexit.register(cleanup)
    
    # Start bot
    logger.info("🚀 Bot polling başlatılıyor...")
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                      ✅ BOT AKTİF!                               ║
║                                                                  ║
║   🤖 @Lunavdsligtg_bot                                          ║
║   📢 {Config.UPDATE_CHANNEL}                           ║
║   💾 SQLite Veritabanı Bağlı                                   ║
║   🚀 Polling: Aktif                                             ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except KeyboardInterrupt:
        logger.warning("⛔ Kullanıcı tarafından durduruldu.")
        cleanup()
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Kritik hata: {e}", exc_info=True)
        logger.info("🔄 5 saniye sonra yeniden başlatılıyor...")
        time.sleep(5)
        os.execl(sys.executable, sys.executable, *sys.argv)
        
        
        #assgidaki bizim vds botun ozellikleri dikkat bu sadece ozellik 
        
        
        import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import json
import logging
import signal
import threading
import re
import sys
import atexit
import requests
import hashlib
import mimetypes
import struct
import asyncio
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Ben luna, Dosya Sunucusuyum."

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Canlı Tutma sunucusu başlatıldı.")
# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = '8668348358:AAF1T_Mqo8ZKJguRAoNSESndB8EGqcyxVFs'
OWNER_ID = 7250471858
ADMIN_ID = 7250471858
YOUR_USERNAME = '@Lunavdsligtg_bot'
UPDATE_CHANNEL = 'https://t.me/glearya'

# Klasör kurulumu - mutlak yollar kullanılarak
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
IROTECH_DIR = os.path.join(BASE_DIR, 'inf')
DATABASE_PATH = os.path.join(IROTECH_DIR, 'bot_data.db')

# File upload limits
FREE_USER_LIMIT = 5
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Gerekli dizinleri oluştur
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Botu başlat
bot = telebot.TeleBot(TOKEN)

# --- Veri yapıları ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False

# --- Kötü Amaçlı Yazılım Algılama Yapılandırması ---
MALWARE_SIGNATURES = [
    b'MZ',  # Windows yürütülebilir dosyası
    b'\x7fELF',  # Linux çalıştırılabilir dosyası
    b'\xfe\xed\xfa',  # Mach-O ikili sistemi
    b'\xce\xfa\xed\xfe',  # Mach-O ikili (ters)
    b'PK',  # ZIP arşivi (şifrelenmiş olabilir)
    b'Rar!',  # RAR arşivi
]

ENCRYPTED_FILE_INDICATORS = [
    b'openssl',
    b'encrypted',
    b'cipher',
    b'AES',
    b'DES',
    b'RSA',
    b'GPG',
    b'PGP',
]

SUSPICIOUS_KEYWORDS = [
    b'ransomware',
    b'trojan',
    b'virus',
    b'malware',
    b'backdoor',
    b'exploit',
    b'payload',
    b'botnet',
    b'keylogger',
    b'rootkit',
]

# --- Günlük Kaydı Ayarları ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Komut Düğmesi Düzenleri (ReplyKeyboardMarkup) ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Güncelleme Kanalı"],
    ["📤 Dosya Yükle", "📂 Dosyalarım"],
    ["⚡ Bot Hızı", "📊 İstatistikler"],
    ["📤 Komut Gönder", "📞 Sahiple İletişim"]
]
ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["📢 Güncelleme Kanalı"],
    ["📤 Dosya Yükle", "📂 Dosyalarım"],
    ["⚡ Bot Hızı", "📊 İstatistikler"],
    ["💳 Abonelikler", "📢 Duyuru"],
    ["🔒 Botu Kilitle", "🟢 Tüm Kodları Çalıştır"],
    ["📤 Komut Gönder", "👑 Yönetici Paneli"],
    ["📞 Sahiple İletişim"]
]

# --- Database Setup ---
def init_db():
    """Initialize the database with required tables"""
    logger.info(f"Veritabanı başlatılıyor: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Veritabanı başarıyla başlatıldı.")
    except Exception as e:
        logger.error(f"❌ Veritabanı başlatma hatası: {e}", exc_info=True)

def load_data():
    """Load data from database into memory"""
    logger.info("Veritabanından veriler yükleniyor...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        # Load subscriptions
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"⚠️ Kullanıcı {user_id} için geçersiz bitiş tarihi formatı: {expiry}. Atlanıyor.")

        # Load user files
        c.execute('SELECT user_id, file_name, file_type FROM user_files')
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        # Load active users
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())

        # Load admins
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        conn.close()
        logger.info(f"Veriler yüklendi: {len(active_users)} kullanıcı, {len(user_subscriptions)} abonelik, {len(admin_ids)} yönetici.")
    except Exception as e:
        logger.error(f"❌ Veri yükleme hatası: {e}", exc_info=True)

# Initialize DB and Load Data at startup
init_db()
load_data()
# --- End Database Setup ---

# --- Malware Detection Functions ---
# Replace the magic import and is_suspicious_file function

def get_file_type(file_content):
    """Determine file type using magic numbers and mimetypes"""
    # Common file signatures
    signatures = {
        b'\x7fELF': 'application/x-executable',
        b'MZ': 'application/x-dosexec',
        b'\xfe\xed\xfa': 'application/x-mach-binary',
        b'\xce\xfa\xed\xfe': 'application/x-mach-binary',
        b'PK': 'application/zip',
        b'Rar!': 'application/x-rar',
    }
    
    for signature, mime_type in signatures.items():
        if file_content.startswith(signature):
            return mime_type
    
    # Fallback to extension-based detection or return unknown
    return 'application/octet-stream'

def is_suspicious_file(file_content, file_name):
    """
    Check if file contains malware signatures, encrypted content, or suspicious keywords.
    Returns (is_suspicious, reason)
    """
    file_lower = file_name.lower()
    
    # Check file extensions first (same as before)
    suspicious_extensions = ['.exe', '.dll', '.bat', '.cmd', '.scr', '.com', '.pif', '.application', '.gadget',
                            '.msi', '.msp', '.com', '.scr', '.hta', '.cpl', '.msc', '.jar', '.bin', '.deb', '.rpm',
                            '.apk', '.app', '.dmg', '.iso', '.img']
    
    if any(file_lower.endswith(ext) for ext in suspicious_extensions):
        return True, f"Şüpheli dosya uzantısı: {file_name}"
    
    # Check for malware signatures in file content
    for signature in MALWARE_SIGNATURES:
        if file_content.startswith(signature):
            return True, f"Kötü amaçlı yazılım imzası tespit edildi: {signature}"
    
    # Check for encrypted file indicators
    sample_size = min(len(file_content), 4096)
    file_sample = file_content[:sample_size]
    
    for indicator in ENCRYPTED_FILE_INDICATORS:
        if indicator in file_sample:
            return True, f"Şifrelenmiş dosya göstergesi: {indicator.decode('utf-8', errors='ignore')}"
    
    # Check for suspicious keywords in first 8KB
    sample_text = file_sample.decode('utf-8', errors='ignore').lower()
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword.decode('utf-8').lower() in sample_text:
            return True, f"Şüpheli kelime bulundu: {keyword.decode('utf-8')}"
    
    # Check file type using our custom function instead of magic
    try:
        file_type = get_file_type(file_sample)
        if file_type in ['application/x-dosexec', 'application/x-executable', 'application/x-mach-binary']:
            return True, f"Çalıştırılabilir dosya türü tespit edildi: {file_type}"
    except Exception as e:
        logger.warning(f"Dosya türü belirlenemedi: {e}")
    
    return False, "Dosya güvenli görünüyor"

def scan_file_for_malware(file_content, file_name, user_id):
    """
    Comprehensive malware scan for uploaded files.
    Only owner can bypass these checks.
    """
    if user_id == OWNER_ID:
        return True, "Sahip güvenlik kontrolünü atladı"
    
    is_suspicious, reason = is_suspicious_file(file_content, file_name)
    
    if is_suspicious:
        logger.warning(f"🚨 {file_name} dosyasında kötü amaçlı yazılım tespit edildi (kullanıcı {user_id}): {reason}")
        return False, f"Güvenlik ihlali: {reason}"
    
    return True, "Dosya güvenlik kontrolünü geçti"

# --- Helper Functions ---
def get_user_folder(user_id):
    """Get or create user's folder for storing files"""
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    """Get the file upload limit for a user"""
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    """Get the number of files uploaded by a user"""
    return len(user_files.get(user_id, []))

def is_bot_running(script_owner_id, file_name):
    """Check if a bot script is currently running for a specific user"""
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            is_running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            if not is_running:
                logger.warning(f"{script_key} için PID {script_info['process'].pid} bulundu ancak çalışmıyor/zombi. Temizleniyor.")
                if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                    try:
                        script_info['log_file'].close()
                    except Exception as log_e:
                        logger.error(f"{script_key} zombie temizliği sırasında log dosyası kapatma hatası: {log_e}")
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            logger.warning(f"{script_key} için işlem bulunamadı (NoSuchProcess). Temizleniyor.")
            if 'log_file' in script_info and hasattr(script_info['log_file'], 'close') and not script_info['log_file'].closed:
                try:
                    script_info['log_file'].close()
                except Exception as log_e:
                    logger.error(f"{script_key} var olmayan işlem temizliği sırasında log dosyası kapatma hatası: {log_e}")
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception as e:
            logger.error(f"{script_key} için işlem durumu kontrol hatası: {e}", exc_info=True)
            return False
    return False

def kill_process_tree(process_info):
    """Kill a process and all its children, ensuring log file is closed."""
    pid = None
    log_file_closed = False
    script_key = process_info.get('script_key', 'N/A')

    try:
        if 'log_file' in process_info and hasattr(process_info['log_file'], 'close') and not process_info['log_file'].closed:
            try:
                process_info['log_file'].close()
                log_file_closed = True
                logger.info(f"{script_key} için log dosyası kapatıldı (PID: {process_info.get('process', {}).get('pid', 'N/A')})")
            except Exception as log_e:
                logger.error(f"{script_key} öldürme sırasında log dosyası kapatma hatası: {log_e}")

        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            if pid:
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                    logger.info(f"{script_key} için işlem ağacı öldürülüyor (PID: {pid}, Çocuklar: {[c.pid for c in children]})")

                    for child in children:
                        try:
                            child.terminate()
                            logger.info(f"{script_key} için çocuk işlem {child.pid} sonlandırıldı")
                        except psutil.NoSuchProcess:
                            logger.warning(f"{script_key} için çocuk işlem {child.pid} zaten gitmiş.")
                        except Exception as e:
                            logger.error(f"{script_key} için çocuk {child.pid} sonlandırma hatası: {e}. Öldürülüyor...")
                            try:
                                child.kill()
                                logger.info(f"{script_key} için çocuk işlem {child.pid} öldürüldü")
                            except Exception as e2:
                                logger.error(f"{script_key} için çocuk {child.pid} öldürülemedi: {e2}")

                    gone, alive = psutil.wait_procs(children, timeout=1)
                    for p in alive:
                        logger.warning(f"{script_key} için çocuk işlem {p.pid} hala aktif. Öldürülüyor.")
                        try:
                            p.kill()
                        except Exception as e:
                            logger.error(f"{script_key} için çocuk {p.pid} bekleme sonrası öldürülemedi: {e}")

                    try:
                        parent.terminate()
                        logger.info(f"{script_key} için ana işlem {pid} sonlandırıldı")
                        try:
                            parent.wait(timeout=1)
                        except psutil.TimeoutExpired:
                            logger.warning(f"{script_key} için ana işlem {pid} sonlanmadı. Öldürülüyor.")
                            parent.kill()
                            logger.info(f"{script_key} için ana işlem {pid} öldürüldü")
                    except psutil.NoSuchProcess:
                        logger.warning(f"{script_key} için ana işlem {pid} zaten gitmiş.")
                    except Exception as e:
                        logger.error(f"{script_key} için ana {pid} sonlandırma hatası: {e}. Öldürülüyor...")
                        try:
                            parent.kill()
                            logger.info(f"{script_key} için ana işlem {pid} öldürüldü")
                        except Exception as e2:
                            logger.error(f"{script_key} için ana {pid} öldürülemedi: {e2}")

                except psutil.NoSuchProcess:
                    logger.warning(f"{script_key} için işlem {pid or 'N/A'} öldürme sırasında bulunamadı. Zaten sonlanmış?")
            else:
                logger.error(f"{script_key} için işlem PID'i None.")
        elif log_file_closed:
            logger.warning(f"{script_key} için işlem nesnesi eksik, ancak log dosyası kapatıldı.")
        else:
            logger.error(f"{script_key} için işlem nesnesi eksik ve log dosyası yok. Öldürülemez.")
    except Exception as e:
        logger.error(f"❌ PID {pid or 'N/A'} ({script_key}) için işlem ağacı öldürülürken beklenmeyen hata: {e}", exc_info=True)

# --- Automatic Package Installation & Script Running ---

def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name) 
    if package_name is None: 
        logger.info(f"'{module_name}' modülü çekirdek. Pip kurulumu atlanıyor.")
        return False 
    try:
        bot.reply_to(message, f"🐍 `{module_name}` modülü bulunamadı. `{package_name}` kuruluyor...", parse_mode='Markdown')
        command = [sys.executable, '-m', 'pip', 'install', package_name]
        logger.info(f"Kurulum çalıştırılıyor: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            logger.info(f"{package_name} kuruldu. Çıktı:\n{result.stdout}")
            bot.reply_to(message, f"✅ `{package_name}` paketi (`{module_name}` için) kuruldu.", parse_mode='Markdown')
            return True
        else:
            error_msg = f"❌ `{module_name}` için `{package_name}` kurulumu başarısız.\nLog:\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (Log kısaltıldı)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return False
    except Exception as e:
        error_msg = f"❌ `{package_name}` kurulurken hata: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def attempt_install_npm(module_name, user_folder, message):
    try:
        bot.reply_to(message, f"🟠 Node paketi `{module_name}` bulunamadı. Yerel olarak kuruluyor...", parse_mode='Markdown')
        command = ['npm', 'install', module_name]
        logger.info(f"npm kurulumu çalıştırılıyor: {' '.join(command)} {user_folder} içinde")
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=user_folder, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            logger.info(f"{module_name} kuruldu. Çıktı:\n{result.stdout}")
            bot.reply_to(message, f"✅ Node paketi `{module_name}` yerel olarak kuruldu.", parse_mode='Markdown')
            return True
        else:
            error_msg = f"❌ Node paketi `{module_name}` kurulumu başarısız.\nLog:\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (Log kısaltıldı)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return False
    except FileNotFoundError:
         error_msg = "❌ Hata: 'npm' bulunamadı. Node.js/npm'in kurulu ve PATH'te olduğundan emin olun."
         logger.error(error_msg)
         bot.reply_to(message, error_msg)
         return False
    except Exception as e:
        error_msg = f"❌ Node paketi `{module_name}` kurulurken hata: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    """Run Python script. script_owner_id is used for the script_key. message_obj_for_reply is for sending feedback."""
    max_attempts = 2 
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ '{file_name}' {max_attempts} denemeden sonra çalıştırılamadı. Logları kontrol edin.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"{script_path} Python betiği çalıştırılıyor (Deneme {attempt}) (Anahtar: {script_key}) kullanıcı {script_owner_id} için")

    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"❌ Hata: '{file_name}' betiği '{script_path}' adresinde bulunamadı!")
             logger.error(f"Betik bulunamadı: {script_path} kullanıcı {script_owner_id} için")
             if script_owner_id in user_files:
                 user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
             remove_user_file_db(script_owner_id, file_name)
             return

        if attempt == 1:
            check_command = [sys.executable, script_path]
            logger.info(f"Python ön kontrolü çalıştırılıyor: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                logger.info(f"Python Ön kontrol erken. RC: {return_code}. Stderr: {stderr[:200]}...")
                if return_code != 0 and stderr:
                    match_py = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match_py:
                        module_name = match_py.group(1).strip().strip("'\"")
                        logger.info(f"Eksik Python modülü tespit edildi: {module_name}")
                        if attempt_install_pip(module_name, message_obj_for_reply):
                            logger.info(f"{module_name} için kurulum tamam. run_script yeniden deneniyor...")
                            bot.reply_to(message_obj_for_reply, f"🔄 Kurulum başarılı. '{file_name}' yeniden deneniyor...")
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"❌ Kurulum başarısız. '{file_name}' çalıştırılamıyor.")
                            return
                    else:
                         error_summary = stderr[:500]
                         bot.reply_to(message_obj_for_reply, f"❌ '{file_name}' için betik ön kontrolünde hata:\n```\n{error_summary}\n```\nBetiği düzeltin.", parse_mode='Markdown')
                         return
            except subprocess.TimeoutExpired:
                logger.info("Python Ön kontrol zaman aşımına uğradı (>5sn), importlar muhtemelen tamam. Kontrol işlemi öldürülüyor.")
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
                logger.info("Python Kontrol işlemi öldürüldü. Uzun çalışmaya devam ediliyor.")
            except FileNotFoundError:
                 logger.error(f"Python yorumlayıcı bulunamadı: {sys.executable}")
                 bot.reply_to(message_obj_for_reply, f"❌ Hata: Python yorumlayıcı '{sys.executable}' bulunamadı.")
                 return
            except Exception as e:
                 logger.error(f"{script_key} için Python ön kontrolünde hata: {e}", exc_info=True)
                 bot.reply_to(message_obj_for_reply, f"❌ '{file_name}' için betik ön kontrolünde beklenmeyen hata: {e}")
                 return
            finally:
                 if check_proc and check_proc.poll() is None:
                     logger.warning(f"Python Kontrol işlemi {check_proc.pid} hala çalışıyor. Öldürülüyor.")
                     check_proc.kill(); check_proc.communicate()

        logger.info(f"{script_key} için uzun çalışan Python işlemi başlatılıyor")
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try: log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
             logger.error(f"{script_key} için '{log_file_path}' log dosyası açılamadı: {e}", exc_info=True)
             bot.reply_to(message_obj_for_reply, f"❌ '{log_file_path}' log dosyası açılamadı: {e}")
             return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                [sys.executable, script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            logger.info(f"{script_key} için Python işlemi {process.pid} başlatıldı")
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ Python betiği '{file_name}' başlatıldı! (PID: {process.pid}) (Kullanıcı: {script_owner_id})")
        except FileNotFoundError:
             logger.error(f"Uzun çalışma için Python yorumlayıcı {sys.executable} bulunamadı {script_key}")
             bot.reply_to(message_obj_for_reply, f"❌ Hata: Python yorumlayıcı '{sys.executable}' bulunamadı.")
             if log_file and not log_file.closed: log_file.close()
             if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            error_msg = f"❌ Python betiği '{file_name}' başlatılırken hata: {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                 logger.warning(f"{script_key} için potansiyel olarak başlatılan Python işlemi {process.pid} öldürülüyor")
                 kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ Python betiği '{file_name}' çalıştırılırken beklenmeyen hata: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
             logger.warning(f"run_script'te hata nedeniyle {script_key} temizleniyor.")
             kill_process_tree(bot_scripts[script_key])
             del bot_scripts[script_key]

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    """Run JS script. script_owner_id is used for the script_key. message_obj_for_reply is for sending feedback."""
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ '{file_name}' {max_attempts} denemeden sonra çalıştırılamadı. Logları kontrol edin.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"{script_path} JS betiği çalıştırılıyor (Deneme {attempt}) (Anahtar: {script_key}) kullanıcı {script_owner_id} için")

    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"❌ Hata: '{file_name}' betiği '{script_path}' adresinde bulunamadı!")
             logger.error(f"JS Betik bulunamadı: {script_path} kullanıcı {script_owner_id} için")
             if script_owner_id in user_files:
                 user_files[script_owner_id] = [f for f in user_files.get(script_owner_id, []) if f[0] != file_name]
             remove_user_file_db(script_owner_id, file_name)
             return

        if attempt == 1:
            check_command = ['node', script_path]
            logger.info(f"JS ön kontrolü çalıştırılıyor: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=5)
                return_code = check_proc.returncode
                logger.info(f"JS Ön kontrol erken. RC: {return_code}. Stderr: {stderr[:200]}...")
                if return_code != 0 and stderr:
                    match_js = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match_js:
                        module_name = match_js.group(1).strip().strip("'\"")
                        if not module_name.startswith('.') and not module_name.startswith('/'):
                             logger.info(f"Eksik Node modülü tespit edildi: {module_name}")
                             if attempt_install_npm(module_name, user_folder, message_obj_for_reply):
                                 logger.info(f"{module_name} için NPM Kurulumu tamam. run_js_script yeniden deneniyor...")
                                 bot.reply_to(message_obj_for_reply, f"🔄 NPM Kurulumu başarılı. '{file_name}' yeniden deneniyor...")
                                 time.sleep(2)
                                 threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                                 return
                             else:
                                 bot.reply_to(message_obj_for_reply, f"❌ NPM Kurulumu başarısız. '{file_name}' çalıştırılamıyor.")
                                 return
                        else: logger.info(f"Göreceli/çekirdek modül için npm kurulumu atlanıyor: {module_name}")
                    error_summary = stderr[:500]
                    bot.reply_to(message_obj_for_reply, f"❌ '{file_name}' için JS betik ön kontrolünde hata:\n```\n{error_summary}\n```\nBetiği düzeltin veya manuel kurun.", parse_mode='Markdown')
                    return
            except subprocess.TimeoutExpired:
                logger.info("JS Ön kontrol zaman aşımına uğradı (>5sn), importlar muhtemelen tamam. Kontrol işlemi öldürülüyor.")
                if check_proc and check_proc.poll() is None: check_proc.kill(); check_proc.communicate()
                logger.info("JS Kontrol işlemi öldürüldü. Uzun çalışmaya devam ediliyor.")
            except FileNotFoundError:
                 error_msg = "❌ Hata: 'node' bulunamadı. JS dosyaları için Node.js'in kurulu olduğundan emin olun."
                 logger.error(error_msg)
                 bot.reply_to(message_obj_for_reply, error_msg)
                 return
            except Exception as e:
                 logger.error(f"{script_key} için JS ön kontrolünde hata: {e}", exc_info=True)
                 bot.reply_to(message_obj_for_reply, f"❌ '{file_name}' için JS ön kontrolünde beklenmeyen hata: {e}")
                 return
            finally:
                 if check_proc and check_proc.poll() is None:
                     logger.warning(f"JS Kontrol işlemi {check_proc.pid} hala çalışıyor. Öldürülüyor.")
                     check_proc.kill(); check_proc.communicate()

        logger.info(f"{script_key} için uzun çalışan JS işlemi başlatılıyor")
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try: log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"{script_key} JS betiği için '{log_file_path}' log dosyası açılamadı: {e}", exc_info=True)
            bot.reply_to(message_obj_for_reply, f"❌ '{log_file_path}' log dosyası açılamadı: {e}")
            return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                ['node', script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
                stdin=subprocess.PIPE, startupinfo=startupinfo, creationflags=creationflags,
                encoding='utf-8', errors='ignore'
            )
            logger.info(f"{script_key} için JS işlemi {process.pid} başlatıldı")
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js', 'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ JS betiği '{file_name}' başlatıldı! (PID: {process.pid}) (Kullanıcı: {script_owner_id})")
        except FileNotFoundError:
             error_msg = "❌ Hata: Uzun çalışma için 'node' bulunamadı. Node.js'in kurulu olduğundan emin olun."
             logger.error(error_msg)
             if log_file and not log_file.closed: log_file.close()
             bot.reply_to(message_obj_for_reply, error_msg)
             if script_key in bot_scripts: del bot_scripts[script_key]
        except Exception as e:
            if log_file and not log_file.closed: log_file.close()
            error_msg = f"❌ JS betiği '{file_name}' başlatılırken hata: {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if process and process.poll() is None:
                 logger.warning(f"{script_key} için potansiyel olarak başlatılan JS işlemi {process.pid} öldürülüyor")
                 kill_process_tree({'process': process, 'log_file': log_file, 'script_key': script_key})
            if script_key in bot_scripts: del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ JS betiği '{file_name}' çalıştırılırken beklenmeyen hata: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)
        if script_key in bot_scripts:
             logger.warning(f"run_js_script'te hata nedeniyle {script_key} temizleniyor.")
             kill_process_tree(bot_scripts[script_key])
             del bot_scripts[script_key]

# --- Map Telegram import names to actual PyPI package names ---
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'telethon.sync': 'telethon',
    'from telethon.sync import telegramclient': 'telethon',
    'telepot': 'telepot',
    'pytg': 'pytg',
    'tgcrypto': 'tgcrypto',
    'telegram_upload': 'telegram-upload',
    'telegram_send': 'telegram-send',
    'telegram_text': 'telegram-text',
    'mtproto': 'telegram-mtproto',
    'tl': 'telethon',
    'telegram_utils': 'telegram-utils',
    'telegram_logger': 'telegram-logger',
    'telegram_handlers': 'python-telegram-handlers',
    'telegram_redis': 'telegram-redis',
    'telegram_sqlalchemy': 'telegram-sqlalchemy',
    'telegram_payment': 'telegram-payment',
    'telegram_shop': 'telegram-shop-sdk',
    'pytest_telegram': 'pytest-telegram',
    'telegram_debug': 'telegram-debug',
    'telegram_scraper': 'telegram-scraper',
    'telegram_analytics': 'telegram-analytics',
    'telegram_nlp': 'telegram-nlp-toolkit',
    'telegram_ai': 'telegram-ai',
    'telegram_api': 'telegram-api-client',
    'telegram_web': 'telegram-web-integration',
    'telegram_games': 'telegram-games',
    'telegram_quiz': 'telegram-quiz-bot',
    'telegram_ffmpeg': 'telegram-ffmpeg',
    'telegram_media': 'telegram-media-utils',
    'telegram_2fa': 'telegram-twofa',
    'telegram_crypto': 'telegram-crypto-bot',
    'telegram_i18n': 'telegram-i18n',
    'telegram_translate': 'telegram-translate',
    'bs4': 'beautifulsoup4',
    'requests': 'requests',
    'pyfiglet': 'pyfiglet',
    'pillow': 'Pillow',
    'cv2': 'opencv-python',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'flask': 'Flask',
    'django': 'Django',
    'sqlalchemy': 'SQLAlchemy',
    'asyncio': None,
    'json': None,
    'datetime': None,
    'os': None,
    'sys': None,
    're': None,
    'time': None,
    'math': None,
    'random': None,
    'logging': None,
    'threading': None,
    'subprocess': None,
    'zipfile': None,
    'tempfile': None,
    'shutil': None,
    'sqlite3': None,
    'psutil': 'psutil',
    'atexit': None
}
# --- End Automatic Package Installation & Script Running ---

# --- Database Operations ---
DB_LOCK = threading.Lock() 

def save_user_file(user_id, file_name, file_type='py'):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)',
                      (user_id, file_name, file_type))
            conn.commit()
            if user_id not in user_files: user_files[user_id] = []
            user_files[user_id] = [(fn, ft) for fn, ft in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type))
            logger.info(f"{user_id} kullanıcısı için '{file_name}' ({file_type}) dosyası kaydedildi")
        except sqlite3.Error as e: logger.error(f"❌ {user_id}, {file_name} için dosya kaydedilirken SQLite hatası: {e}")
        except Exception as e: logger.error(f"❌ {user_id}, {file_name} için dosya kaydedilirken beklenmeyen hata: {e}", exc_info=True)
        finally: conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
                if not user_files[user_id]: del user_files[user_id]
            logger.info(f"{user_id} kullanıcısı için '{file_name}' dosyası veritabanından kaldırıldı")
        except sqlite3.Error as e: logger.error(f"❌ {user_id}, {file_name} için dosya kaldırılırken SQLite hatası: {e}")
        except Exception as e: logger.error(f"❌ {user_id}, {file_name} için dosya kaldırılırken beklenmeyen hata: {e}", exc_info=True)
        finally: conn.close()

def add_active_user(user_id):
    active_users.add(user_id) 
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
            logger.info(f"Aktif kullanıcı {user_id} veritabanına eklendi/onaylandı")
        except sqlite3.Error as e: logger.error(f"❌ Aktif kullanıcı {user_id} eklenirken SQLite hatası: {e}")
        except Exception as e: logger.error(f"❌ Aktif kullanıcı {user_id} eklenirken beklenmeyen hata: {e}", exc_info=True)
        finally: conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
            logger.info(f"{user_id} için abonelik kaydedildi, bitiş {expiry_str}")
        except sqlite3.Error as e: logger.error(f"❌ {user_id} için abonelik kaydedilirken SQLite hatası: {e}")
        except Exception as e: logger.error(f"❌ {user_id} için abonelik kaydedilirken beklenmeyen hata: {e}", exc_info=True)
        finally: conn.close()

def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
            conn.commit()
            if user_id in user_subscriptions: del user_subscriptions[user_id]
            logger.info(f"{user_id} için abonelik veritabanından kaldırıldı")
        except sqlite3.Error as e: logger.error(f"❌ {user_id} için abonelik kaldırılırken SQLite hatası: {e}")
        except Exception as e: logger.error(f"❌ {user_id} için abonelik kaldırılırken beklenmeyen hata: {e}", exc_info=True)
        finally: conn.close()

def add_admin_db(admin_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (admin_id,))
            conn.commit()
            admin_ids.add(admin_id) 
            logger.info(f"Yönetici {admin_id} veritabanına eklendi")
        except sqlite3.Error as e: logger.error(f"❌ Yönetici {admin_id} eklenirken SQLite hatası: {e}")
        except Exception as e: logger.error(f"❌ Yönetici {admin_id} eklenirken beklenmeyen hata: {e}", exc_info=True)
        finally: conn.close()

def remove_admin_db(admin_id):
    if admin_id == OWNER_ID:
        logger.warning("Sahip ID'si yöneticilerden kaldırılmaya çalışıldı.")
        return False 
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        removed = False
        try:
            c.execute('SELECT 1 FROM admins WHERE user_id = ?', (admin_id,))
            if c.fetchone():
                c.execute('DELETE FROM admins WHERE user_id = ?', (admin_id,))
                conn.commit()
                removed = c.rowcount > 0 
                if removed: admin_ids.discard(admin_id); logger.info(f"Yönetici {admin_id} veritabanından kaldırıldı")
                else: logger.warning(f"Yönetici {admin_id} bulundu ancak silme 0 satır etkiledi.")
            else:
                logger.warning(f"Yönetici {admin_id} veritabanında bulunamadı.")
                admin_ids.discard(admin_id)
            return removed
        except sqlite3.Error as e: logger.error(f"❌ Yönetici {admin_id} kaldırılırken SQLite hatası: {e}"); return False
        except Exception as e: logger.error(f"❌ Yönetici {admin_id} kaldırılırken beklenmeyen hata: {e}", exc_info=True); return False
        finally: conn.close()
# --- End Database Operations ---

# --- Menu creation (Inline and ReplyKeyboards) ---
def create_main_menu_inline(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton('📢 Güncelleme Kanalı', url=UPDATE_CHANNEL),
        types.InlineKeyboardButton('📤 Dosya Yükle', callback_data='upload'),
        types.InlineKeyboardButton('📂 Dosyalarım', callback_data='check_files'),
        types.InlineKeyboardButton('⚡ Bot Hızı', callback_data='speed'),
        types.InlineKeyboardButton('📤 Komut Gönder', callback_data='send_command'),
        types.InlineKeyboardButton('📞 Sahiple İletişim', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}')
    ]

    if user_id in admin_ids:
        admin_buttons = [
            types.InlineKeyboardButton('💳 Abonelikler', callback_data='subscription'),
            types.InlineKeyboardButton('📊 İstatistikler', callback_data='stats'),
            types.InlineKeyboardButton('🔒 Botu Kilitle' if not bot_locked else '🔓 Kilidi Aç',
                                     callback_data='lock_bot' if not bot_locked else 'unlock_bot'),
            types.InlineKeyboardButton('📢 Duyuru', callback_data='broadcast'),
            types.InlineKeyboardButton('👑 Yönetici Paneli', callback_data='admin_panel'),
            types.InlineKeyboardButton('🟢 Tüm Kullanıcı Betiklerini Çalıştır', callback_data='run_all_scripts')
        ]
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3], admin_buttons[0])
        markup.add(admin_buttons[1], admin_buttons[3])
        markup.add(admin_buttons[2], admin_buttons[5])
        markup.add(buttons[4])
        markup.add(admin_buttons[4])
        markup.add(buttons[5])
    else:
        markup.add(buttons[0])
        markup.add(buttons[1], buttons[2])
        markup.add(buttons[3])
        markup.add(buttons[4])
        markup.add(types.InlineKeyboardButton('📊 İstatistikler', callback_data='stats'))
        markup.add(buttons[5])
    return markup

def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    for row_buttons_text in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row_buttons_text])
    return markup

def create_control_buttons(script_owner_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("🔴 Durdur", callback_data=f'stop_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 Yeniden Başlat", callback_data=f'restart_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("🗑️ Sil", callback_data=f'delete_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("📜 Loglar", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🟢 Başlat", callback_data=f'start_{script_owner_id}_{file_name}'),
            types.InlineKeyboardButton("🗑️ Sil", callback_data=f'delete_{script_owner_id}_{file_name}')
        )
        markup.row(
            types.InlineKeyboardButton("📜 Logları Görüntüle", callback_data=f'logs_{script_owner_id}_{file_name}')
        )
    markup.add(types.InlineKeyboardButton("🔙 Dosyalara Dön", callback_data='check_files'))
    return markup

def create_admin_panel():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Yönetici Ekle', callback_data='add_admin'),
        types.InlineKeyboardButton('➖ Yönetici Kaldır', callback_data='remove_admin')
    )
    markup.row(types.InlineKeyboardButton('📋 Yöneticileri Listele', callback_data='list_admins'))
    markup.row(types.InlineKeyboardButton('🔙 Ana Menüye Dön', callback_data='back_to_main'))
    return markup

def create_subscription_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('➕ Abonelik Ekle', callback_data='add_subscription'),
        types.InlineKeyboardButton('➖ Abonelik Kaldır', callback_data='remove_subscription')
    )
    markup.row(types.InlineKeyboardButton('🔍 Abonelik Sorgula', callback_data='check_subscription'))
    markup.row(types.InlineKeyboardButton('🔙 Ana Menüye Dön', callback_data='back_to_main'))
    return markup

def create_send_command_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        types.InlineKeyboardButton('📝 İşleme Gönder', callback_data='send_to_process'),
        types.InlineKeyboardButton('🔍 Tüm Logları Görüntüle', callback_data='view_all_logs')
    )
    markup.row(types.InlineKeyboardButton('🔙 Ana Menüye Dön', callback_data='back_to_main'))
    return markup
# --- End Menu Creation ---

# --- File Handling with Malware Detection ---
def handle_zip_file(downloaded_file_content, file_name_zip, message):
    user_id = message.from_user.id
    user_folder = get_user_folder(user_id)
    temp_dir = None
    
    # Security check for ZIP files (except owner)
    if user_id != OWNER_ID:
        is_safe, reason = scan_file_for_malware(downloaded_file_content, file_name_zip, user_id)
        if not is_safe:
            bot.reply_to(message, f"🚨 Güvenlik Uyarısı: {reason}\nBu tür dosyayı sadece sahip yükleyebilir.")
            return
    
    try:
        temp_dir = tempfile.mkdtemp(prefix=f"user_{user_id}_zip_")
        logger.info(f"Zip için geçici dizin: {temp_dir}")
        zip_path = os.path.join(temp_dir, file_name_zip)
        with open(zip_path, 'wb') as new_file:
            new_file.write(downloaded_file_content)
        
        # Open Zip to Extract
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Additional security check on content
            if user_id != OWNER_ID:
                for member in zip_ref.infolist():
                    member_name_lower = member.filename.lower()
                    suspicious_extensions = ['.exe', '.dll', '.bat', '.cmd', '.scr', '.com']
                    if any(member_name_lower.endswith(ext) for ext in suspicious_extensions):
                        bot.reply_to(message, f"🚨 Güvenlik Uyarısı: ZIP şüpheli dosya içeriyor: {member.filename}\nBu tür dosyaları sadece sahip yükleyebilir.")
                        return
                    
                    # Check for path traversal
                    member_path = os.path.abspath(os.path.join(temp_dir, member.filename))
                    if not member_path.startswith(os.path.abspath(temp_dir)):
                        raise zipfile.BadZipFile(f"Zip güvensiz yol içeriyor: {member.filename}")
            
            # Extract everything
            zip_ref.extractall(temp_dir)
            logger.info(f"Zip {temp_dir} dizinine çıkarıldı")

        # --- FIX: Recursively find script if not in root (ignores __MACOSX) ---
        target_dir = temp_dir
        root_files = os.listdir(target_dir)
        
        # Check if script exists in root
        if not any(f.endswith(('.py', '.js')) for f in root_files):
            # Recursively search for a folder containing .py or .js
            for root, dirs, files in os.walk(temp_dir):
                # Ignore system/hidden folders like __MACOSX or .git
                dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('__')]
                
                if any(f.endswith(('.py', '.js')) for f in files):
                    target_dir = root
                    break
        
        # If the script is in a subdirectory, move everything up to temp_dir
        if target_dir != temp_dir:
            logger.info(f"Çıkarılan dosyalar {target_dir} konumundan {temp_dir} konumuna düzleştiriliyor")
            for item in os.listdir(target_dir):
                s = os.path.join(target_dir, item)
                d = os.path.join(temp_dir, item)
                # Overwrite if exists (shouldn't happen often in this temp context)
                if os.path.exists(d):
                    if os.path.isdir(d): shutil.rmtree(d)
                    else: os.remove(d)
                shutil.move(s, d)
            # Refresh list after flattening
            extracted_items = os.listdir(temp_dir)
        else:
            extracted_items = root_files
        # --- END FIX ---

        py_files = [f for f in extracted_items if f.endswith('.py')]
        js_files = [f for f in extracted_items if f.endswith('.js')]
        req_file = 'requirements.txt' if 'requirements.txt' in extracted_items else None
        pkg_json = 'package.json' if 'package.json' in extracted_items else None

        if req_file:
            req_path = os.path.join(temp_dir, req_file)
            logger.info(f"requirements.txt bulundu, kurulum: {req_path}")
            bot.reply_to(message, f"🔄 Python bağımlılıkları `{req_file}` dosyasından kuruluyor...")
            try:
                command = [sys.executable, '-m', 'pip', 'install', '-r', req_path]
                result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore')
                logger.info(f"requirements.txt'den pip kurulumu tamam. Çıktı:\n{result.stdout}")
                bot.reply_to(message, f"✅ Python bağımlılıkları `{req_file}` dosyasından kuruldu.")
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ `{req_file}` dosyasından Python bağımlılıkları kurulumu başarısız.\nLog:\n```\n{e.stderr or e.stdout}\n```"
                logger.error(error_msg)
                if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (Log kısaltıldı)"
                bot.reply_to(message, error_msg, parse_mode='Markdown'); return
            except Exception as e:
                 error_msg = f"❌ Python bağımlılıkları kurulurken beklenmeyen hata: {e}"
                 logger.error(error_msg, exc_info=True); bot.reply_to(message, error_msg); return

        if pkg_json:
            logger.info(f"package.json bulundu, npm kurulumu: {temp_dir}")
            bot.reply_to(message, f"🔄 Node bağımlılıkları `{pkg_json}` dosyasından kuruluyor...")
            try:
                command = ['npm', 'install']
                result = subprocess.run(command, capture_output=True, text=True, check=True, cwd=temp_dir, encoding='utf-8', errors='ignore')
                logger.info(f"npm kurulumu tamam. Çıktı:\n{result.stdout}")
                bot.reply_to(message, f"✅ Node bağımlılıkları `{pkg_json}` dosyasından kuruldu.")
            except FileNotFoundError:
                bot.reply_to(message, "❌ 'npm' bulunamadı. Node bağımlılıkları kurulamıyor."); return 
            except subprocess.CalledProcessError as e:
                error_msg = f"❌ `{pkg_json}` dosyasından Node bağımlılıkları kurulumu başarısız.\nLog:\n```\n{e.stderr or e.stdout}\n```"
                logger.error(error_msg)
                if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (Log kısaltıldı)"
                bot.reply_to(message, error_msg, parse_mode='Markdown'); return
            except Exception as e:
                 error_msg = f"❌ Node bağımlılıkları kurulurken beklenmeyen hata: {e}"
                 logger.error(error_msg, exc_info=True); bot.reply_to(message, error_msg); return

        main_script_name = None; file_type = None
        preferred_py = ['main.py', 'bot.py', 'app.py']; preferred_js = ['index.js', 'main.js', 'bot.js', 'app.js']
        for p in preferred_py:
            if p in py_files: main_script_name = p; file_type = 'py'; break
        if not main_script_name:
             for p in preferred_js:
                 if p in js_files: main_script_name = p; file_type = 'js'; break
        if not main_script_name:
            if py_files: main_script_name = py_files[0]; file_type = 'py'
            elif js_files: main_script_name = js_files[0]; file_type = 'js'
        if not main_script_name:
            bot.reply_to(message, "❌ Arşivde `.py` veya `.js` betiği bulunamadı!"); return

        logger.info(f"Çıkarılan dosyalar {temp_dir} konumundan {user_folder} konumuna taşınıyor")
        moved_count = 0
        for item_name in os.listdir(temp_dir):
            if item_name == file_name_zip: continue # Don't move the zip file itself if it's there
            src_path = os.path.join(temp_dir, item_name)
            dest_path = os.path.join(user_folder, item_name)
            if os.path.isdir(dest_path): shutil.rmtree(dest_path)
            elif os.path.exists(dest_path): os.remove(dest_path)
            shutil.move(src_path, dest_path); moved_count +=1
        logger.info(f"{moved_count} öğe {user_folder} konumuna taşındı")

        save_user_file(user_id, main_script_name, file_type)
        logger.info(f"{user_id} için zip'den ana betik '{main_script_name}' ({file_type}) kaydedildi.")
        main_script_path = os.path.join(user_folder, main_script_name)
        bot.reply_to(message, f"✅ Dosyalar çıkarıldı. Ana betik başlatılıyor: `{main_script_name}`...", parse_mode='Markdown')

        if file_type == 'py':
             threading.Thread(target=run_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()
        elif file_type == 'js':
             threading.Thread(target=run_js_script, args=(main_script_path, user_id, user_folder, main_script_name, message)).start()

    except zipfile.BadZipFile as e:
        logger.error(f"{user_id} için geçersiz zip dosyası: {e}")
        bot.reply_to(message, f"❌ Hata: Geçersiz/bozuk ZIP. {e}")
    except Exception as e:
        logger.error(f"❌ {user_id} için zip işlenirken hata: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Zip işlenirken hata: {str(e)}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try: shutil.rmtree(temp_dir); logger.info(f"Geçici dizin temizlendi: {temp_dir}")
            except Exception as e: logger.error(f"Geçici dizin {temp_dir} temizlenemedi: {e}", exc_info=True)
def handle_js_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'js')
        threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ {script_owner_id} için JS dosyası {file_name} işlenirken hata: {e}", exc_info=True)
        bot.reply_to(message, f"❌ JS dosyası işlenirken hata: {str(e)}")

def handle_py_file(file_path, script_owner_id, user_folder, file_name, message):
    try:
        save_user_file(script_owner_id, file_name, 'py')
        threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, message)).start()
    except Exception as e:
        logger.error(f"❌ {script_owner_id} için Python dosyası {file_name} işlenirken hata: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Python dosyası işlenirken hata: {str(e)}")

# --- Send Command and Enhanced Logs Functions ---
def _logic_send_command(message):
    """Handle send command functionality"""
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot yönetici tarafından kilitlendi.")
        return
        
    bot.reply_to(message, "📤 Komut Gönderme Seçenekleri:", reply_markup=create_send_command_menu())

def send_to_process_init(message):
    """Initialize process for sending command to a running script"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Get user's running processes
    user_running_scripts = []
    for script_key, script_info in bot_scripts.items():
        script_owner_id = script_info['script_owner_id']
        if (user_id == script_owner_id or user_id in admin_ids) and is_bot_running(script_owner_id, script_info['file_name']):
            user_running_scripts.append((script_key, script_info))
    
    if not user_running_scripts:
        bot.reply_to(message, "❌ Çalışan betik bulunamadı.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for script_key, script_info in user_running_scripts:
        btn_text = f"{script_info['file_name']} (Kullanıcı: {script_info['script_owner_id']})"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'sendcmd_select_{script_key}'))
    
    markup.add(types.InlineKeyboardButton("🔙 Geri", callback_data='send_command'))
    bot.reply_to(message, "📝 Komut göndermek için çalışan bir betik seçin:", reply_markup=markup)

def process_send_command(message, script_key):
    """Process the actual command to send to the script"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if script_key not in bot_scripts:
        bot.reply_to(message, "❌ Betik artık çalışmıyor.")
        return
    
    script_info = bot_scripts[script_key]
    command_text = message.text
    
    try:
        process = script_info['process']
        if process and process.poll() is None:
            # Send command to process stdin
            process.stdin.write(command_text + '\n')
            process.stdin.flush()
            bot.reply_to(message, f"✅ Komut `{script_info['file_name']}` betiğine gönderildi:\n`{command_text}`", parse_mode='Markdown')
            
            # Wait a bit and check if process is still running
            time.sleep(1)
            if process.poll() is not None:
                bot.reply_to(message, f"⚠️ `{script_info['file_name']}` betiği komut aldıktan sonra durdu.")
        else:
            bot.reply_to(message, f"❌ `{script_info['file_name']}` betiği çalışmıyor.")
    except Exception as e:
        logger.error(f"{script_key} komut gönderme hatası: {e}")
        bot.reply_to(message, f"❌ Komut gönderme hatası: {str(e)}")

def view_all_logs(message):
    """Show all available logs for user"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    user_logs = []
    
    # Get user's folder and all log files
    user_folder = get_user_folder(user_id)
    if os.path.exists(user_folder):
        for file in os.listdir(user_folder):
            if file.endswith('.log'):
                log_path = os.path.join(user_folder, file)
                file_size = os.path.getsize(log_path)
                user_logs.append((file, file_size, log_path))
    
    if not user_logs:
        bot.reply_to(message, "📜 Log dosyası bulunamadı.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for log_file, size, log_path in sorted(user_logs):
        size_kb = size / 1024
        btn_text = f"{log_file} ({size_kb:.1f} KB)"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'viewlog_{user_id}_{log_file}'))
    
    markup.add(types.InlineKeyboardButton("🔙 Geri", callback_data='send_command'))
    bot.reply_to(message, "📜 Mevcut Log Dosyaları:", reply_markup=markup)

def send_log_file(message, log_path, log_filename):
    """Send log file as document"""
    try:
        file_size = os.path.getsize(log_path)
        if file_size > 50 * 1024 * 1024:  # 50MB limit
            bot.reply_to(message, f"❌ Log dosyası çok büyük ({file_size/1024/1024:.1f} MB). Maksimum 50MB.")
            return
        
        with open(log_path, 'rb') as log_file:
            bot.send_document(message.chat.id, log_file, caption=f"📜 {log_filename}")
            
    except Exception as e:
        logger.error(f"Log dosyası gönderme hatası {log_path}: {e}")
        bot.reply_to(message, f"❌ Log dosyası gönderme hatası: {str(e)}")

# --- Logic Functions (called by commands and text handlers) ---
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username

    logger.info(f"Hoş geldin isteği user_id: {user_id}, kullanıcı adı: @{user_username}")

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ Bot yönetici tarafından kilitlendi. Daha sonra deneyin.")
        return

    user_bio = "Biyografi alınamadı"; photo_file_id = None
    try: user_bio = bot.get_chat(user_id).bio or "Biyografi yok"
    except Exception: pass
    try:
        user_profile_photos = bot.get_user_profile_photos(user_id, limit=1)
        if user_profile_photos.photos: photo_file_id = user_profile_photos.photos[0][-1].file_id
    except Exception: pass

    if user_id not in active_users:
        add_active_user(user_id)
        try:
            owner_notification = (f"🎉 Yeni kullanıcı!\n👤 İsim: {user_name}\n✳️ Kullanıcı: @{user_username or 'N/A'}\n"
                                  f"🆔 ID: `{user_id}`\n📝 Biyografi: {user_bio}")
            bot.send_message(OWNER_ID, owner_notification, parse_mode='Markdown')
            if photo_file_id: bot.send_photo(OWNER_ID, photo_file_id, caption=f"Yeni kullanıcı {user_id} fotoğrafı")
        except Exception as e: logger.error(f"⚠️ Yeni kullanıcı {user_id} hakkında sahibi bilgilendirilemedi: {e}")

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Sınırsız"
    expiry_info = ""
    if user_id == OWNER_ID: user_status = "👑 Sahip"
    elif user_id in admin_ids: user_status = "🛡️ Yönetici"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"; days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⏳ Abonelik bitiş: {days_left} gün kaldı"
        else: user_status = "🆓 Ücretsiz Kullanıcı (Süresi Dolmuş)"; remove_subscription_db(user_id)
    else: user_status = "🆓 Ücretsiz Kullanıcı"

    welcome_msg_text = (f"〽️ Hoş geldin, {user_name}!\n\n🆔 Kullanıcı ID'n: `{user_id}`\n"
                        f"✳️ Kullanıcı Adı: `@{user_username or 'Ayarlanmamış'}`\n"
                        f"🔰 Durumun: {user_status}{expiry_info}\n"
                        f"📁 Yüklenen Dosyalar: {current_files} / {limit_str}\n\n"
                        f"🤖 Python (`.py`) veya JS (`.js`) betiklerini barındır ve çalıştır.\n"
                        f"   Tek dosya veya `.zip` arşivi yükleyin.\n\n"
                        f"👇 Butonları kullanın veya komut yazın.")
    main_reply_markup = create_reply_keyboard_main_menu(user_id)
    try:
        if photo_file_id: bot.send_photo(chat_id, photo_file_id)
        bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"{user_id} için hoş geldin mesajı gönderilirken hata: {e}", exc_info=True)
        try: bot.send_message(chat_id, welcome_msg_text, reply_markup=main_reply_markup, parse_mode='Markdown')
        except Exception as fallback_e: logger.error(f"{user_id} için yedek mesaj gönderimi başarısız: {fallback_e}")

def _logic_updates_channel(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📢 Güncelleme Kanalı', url=UPDATE_CHANNEL))
    bot.reply_to(message, "Güncelleme Kanalımızı Ziyaret Edin:", reply_markup=markup)

def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ Bot yönetici tarafından kilitlendi, dosya kabul edilmiyor.")
        return

    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Sınırsız"
        bot.reply_to(message, f"⚠️ Dosya limitine ulaşıldı ({current_files}/{limit_str}). Önce dosya silin.")
        return
    bot.reply_to(message, "📤 Python (`.py`), JS (`.js`) veya ZIP (`.zip`) dosyanızı gönderin.")

def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(message, "📂 Dosyalarınız:\n\n(Henüz dosya yüklenmemiş)")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Çalışıyor" if is_running else "🔴 Durduruldu"
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    bot.reply_to(message, "📂 Dosyalarınız:\nYönetmek için tıklayın.", reply_markup=markup, parse_mode='Markdown')

def _logic_bot_speed(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    start_time_ping = time.time()
    wait_msg = bot.reply_to(message, "🏃 Hız test ediliyor...")
    try:
        bot.send_chat_action(chat_id, 'typing')
        response_time = round((time.time() - start_time_ping) * 1000, 2)
        status = "🔓 Kilit Açık" if not bot_locked else "🔒 Kilitli"
        if user_id == OWNER_ID: user_level = "👑 Sahip"
        elif user_id in admin_ids: user_level = "🛡️ Yönetici"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now(): user_level = "⭐ Premium"
        else: user_level = "🆓 Ücretsiz Kullanıcı"
        speed_msg = (f"⚡ Bot Hızı ve Durumu:\n\n⏱️ API Yanıt Süresi: {response_time} ms\n"
                     f"🚦 Bot Durumu: {status}\n"
                     f"👤 Seviyeniz: {user_level}")
        bot.edit_message_text(speed_msg, chat_id, wait_msg.message_id)
    except Exception as e:
        logger.error(f"Hız testi sırasında hata (komut): {e}", exc_info=True)
        bot.edit_message_text("❌ Hız testi sırasında hata oluştu.", chat_id, wait_msg.message_id)

def _logic_contact_owner(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('📞 Sahiple İletişim', url=f'https://t.me/{YOUR_USERNAME.replace("@", "")}'))
    bot.reply_to(message, "Sahiple iletişime geçmek için tıklayın:", reply_markup=markup)

# --- Admin Logic Functions ---
def _logic_subscriptions_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Yönetici yetkisi gerekli.")
        return
    bot.reply_to(message, "💳 Abonelik Yönetimi\n/start veya yönetici komut menüsünden butonları kullanın.", reply_markup=create_subscription_menu())

def _logic_statistics(message):
    user_id = message.from_user.id
    total_users = len(active_users)
    total_files_records = sum(len(files) for files in user_files.values())

    running_bots_count = 0
    user_running_bots = 0

    for script_key_iter, script_info_iter in list(bot_scripts.items()):
        s_owner_id, _ = script_key_iter.split('_', 1)
        if is_bot_running(int(s_owner_id), script_info_iter['file_name']):
            running_bots_count += 1
            if int(s_owner_id) == user_id:
                user_running_bots +=1

    stats_msg_base = (f"📊 Bot İstatistikleri:\n\n"
                      f"👥 Toplam Kullanıcı: {total_users}\n"
                      f"📂 Toplam Dosya Kaydı: {total_files_records}\n"
                      f"🟢 Toplam Aktif Bot: {running_bots_count}\n")

    if user_id in admin_ids:
        stats_msg_admin = (f"🔒 Bot Durumu: {'🔴 Kilitli' if bot_locked else '🟢 Kilit Açık'}\n"
                           f"🤖 Çalışan Botlarınız: {user_running_bots}")
        stats_msg = stats_msg_base + stats_msg_admin
    else:
        stats_msg = stats_msg_base + f"🤖 Çalışan Botlarınız: {user_running_bots}"

    bot.reply_to(message, stats_msg)

def _logic_broadcast_init(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Yönetici yetkisi gerekli.")
        return
    msg = bot.reply_to(message, "📢 Tüm aktif kullanıcılara duyuru mesajını gönderin.\n/cancel ile iptal edin.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def _logic_toggle_lock_bot(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Yönetici yetkisi gerekli.")
        return
    global bot_locked
    bot_locked = not bot_locked
    status = "kilitlendi" if bot_locked else "kilidi açıldı"
    logger.warning(f"Bot {status} Yönetici {message.from_user.id} tarafından komut/buton ile.")
    bot.reply_to(message, f"🔒 Bot {status}.")

def _logic_admin_panel(message):
    if message.from_user.id not in admin_ids:
        bot.reply_to(message, "⚠️ Yönetici yetkisi gerekli.")
        return
    bot.reply_to(message, "👑 Yönetici Paneli\nYöneticileri yönetin. /start veya yönetici menüsünden butonları kullanın.",
                 reply_markup=create_admin_panel())

def _logic_run_all_scripts(message_or_call):
    if isinstance(message_or_call, telebot.types.Message):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.chat.id
        reply_func = lambda text, **kwargs: bot.reply_to(message_or_call, text, **kwargs)
        admin_message_obj_for_script_runner = message_or_call
    elif isinstance(message_or_call, telebot.types.CallbackQuery):
        admin_user_id = message_or_call.from_user.id
        admin_chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
        reply_func = lambda text, **kwargs: bot.send_message(admin_chat_id, text, **kwargs)
        admin_message_obj_for_script_runner = message_or_call.message 
    else:
        logger.error("_logic_run_all_scripts için geçersiz argüman")
        return

    if admin_user_id not in admin_ids:
        reply_func("⚠️ Yönetici yetkisi gerekli.")
        return

    reply_func("⏳ Tüm kullanıcı betiklerini çalıştırma işlemi başlatılıyor. Bu biraz zaman alabilir...")
    logger.info(f"Yönetici {admin_user_id} 'tüm betikleri çalıştır' işlemini {admin_chat_id} sohbetinden başlattı.")

    started_count = 0; attempted_users = 0; skipped_files = 0; error_files_details = []

    all_user_files_snapshot = dict(user_files)

    for target_user_id, files_for_user in all_user_files_snapshot.items():
        if not files_for_user: continue
        attempted_users += 1
        logger.info(f"{target_user_id} kullanıcısı için betikler işleniyor...")
        user_folder = get_user_folder(target_user_id)

        for file_name, file_type in files_for_user:
            if not is_bot_running(target_user_id, file_name):
                file_path = os.path.join(user_folder, file_name)
                if os.path.exists(file_path):
                    logger.info(f"Yönetici {admin_user_id}, {target_user_id} kullanıcısı için '{file_name}' ({file_type}) başlatmayı deniyor.")
                    try:
                        if file_type == 'py':
                            threading.Thread(target=run_script, args=(file_path, target_user_id, user_folder, file_name, admin_message_obj_for_script_runner)).start()
                            started_count += 1
                        elif file_type == 'js':
                            threading.Thread(target=run_js_script, args=(file_path, target_user_id, user_folder, file_name, admin_message_obj_for_script_runner)).start()
                            started_count += 1
                        else:
                            logger.warning(f"{file_name} (kullanıcı {target_user_id}) için bilinmeyen dosya türü '{file_type}'. Atlanıyor.")
                            error_files_details.append(f"`{file_name}` (Kullanıcı {target_user_id}) - Bilinmeyen tür")
                            skipped_files += 1
                        time.sleep(0.7)
                    except Exception as e:
                        logger.error(f"'{file_name}' (kullanıcı {target_user_id}) başlatma kuyruğa alma hatası: {e}")
                        error_files_details.append(f"`{file_name}` (Kullanıcı {target_user_id}) - Başlatma hatası")
                        skipped_files += 1
                else:
                    logger.warning(f"{target_user_id} kullanıcısı için '{file_name}' dosyası '{file_path}' adresinde bulunamadı. Atlanıyor.")
                    error_files_details.append(f"`{file_name}` (Kullanıcı {target_user_id}) - Dosya bulunamadı")
                    skipped_files += 1

    summary_msg = (f"✅ Tüm Kullanıcı Betikleri - İşlem Tamamlandı:\n\n"
                   f"▶️ Başlatılmaya çalışılan: {started_count} betik.\n"
                   f"👥 İşlenen kullanıcı: {attempted_users}.\n")
    if skipped_files > 0:
        summary_msg += f"⚠️ Atlanan/Hatalı dosyalar: {skipped_files}\n"
        if error_files_details:
             summary_msg += "Detaylar (ilk 5):\n" + "\n".join([f"  - {err}" for err in error_files_details[:5]])
             if len(error_files_details) > 5: summary_msg += "\n  ... ve daha fazlası (logları kontrol edin)."

    reply_func(summary_msg, parse_mode='Markdown')
    logger.info(f"Tüm betikleri çalıştır işlemi tamamlandı. Yönetici: {admin_user_id}. Başlatılan: {started_count}. Atlanan/Hata: {skipped_files}")

# --- Command Handlers & Text Handlers for ReplyKeyboard ---
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message): _logic_send_welcome(message)

@bot.message_handler(commands=['status'])
def command_show_status(message): _logic_statistics(message)

BUTTON_TEXT_TO_LOGIC = {
    "📢 Güncelleme Kanalı": _logic_updates_channel,
    "📤 Dosya Yükle": _logic_upload_file,
    "📂 Dosyalarım": _logic_check_files,
    "⚡ Bot Hızı": _logic_bot_speed,
    "📤 Komut Gönder": _logic_send_command,
    "📞 Sahiple İletişim": _logic_contact_owner,
    "📊 İstatistikler": _logic_statistics,
    "💳 Abonelikler": _logic_subscriptions_panel,
    "📢 Duyuru": _logic_broadcast_init,
    "🔒 Botu Kilitle": _logic_toggle_lock_bot,
    "🟢 Tüm Kodları Çalıştır": _logic_run_all_scripts,
    "👑 Yönetici Paneli": _logic_admin_panel,
}

@bot.message_handler(func=lambda message: message.text in BUTTON_TEXT_TO_LOGIC)
def handle_button_text(message):
    logic_func = BUTTON_TEXT_TO_LOGIC.get(message.text)
    if logic_func: logic_func(message)
    else: logger.warning(f"Buton metni '{message.text}' eşleşti ancak mantık fonksiyonu yok.")

@bot.message_handler(commands=['updateschannel'])
def command_updates_channel(message): _logic_updates_channel(message)
@bot.message_handler(commands=['uploadfile'])
def command_upload_file(message): _logic_upload_file(message)
@bot.message_handler(commands=['checkfiles'])
def command_check_files(message): _logic_check_files(message)
@bot.message_handler(commands=['botspeed'])
def command_bot_speed(message): _logic_bot_speed(message)
@bot.message_handler(commands=['sendcommand'])
def command_send_command(message): _logic_send_command(message)
@bot.message_handler(commands=['contactowner'])
def command_contact_owner(message): _logic_contact_owner(message)
@bot.message_handler(commands=['subscriptions'])
def command_subscriptions(message): _logic_subscriptions_panel(message)
@bot.message_handler(commands=['statistics'])
def command_statistics(message): _logic_statistics(message)
@bot.message_handler(commands=['broadcast'])
def command_broadcast(message): _logic_broadcast_init(message)
@bot.message_handler(commands=['lockbot']) 
def command_lock_bot(message): _logic_toggle_lock_bot(message)
@bot.message_handler(commands=['adminpanel'])
def command_admin_panel(message): _logic_admin_panel(message)
@bot.message_handler(commands=['runningallcode'])
def command_run_all_code(message): _logic_run_all_scripts(message)

@bot.message_handler(commands=['ping'])
def ping(message):
    start_ping_time = time.time() 
    msg = bot.reply_to(message, "Pong!")
    latency = round((time.time() - start_ping_time) * 1000, 2)
    bot.edit_message_text(f"Pong! Gecikme: {latency} ms", message.chat.id, msg.message_id)

# --- Document (File) Handler with Malware Detection ---
@bot.message_handler(content_types=['document'])
def handle_file_upload_doc(message):
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        doc = message.document

        logger.info(f"{user_id} kullanıcısından dosya: {doc.file_name} ({doc.mime_type}), Boyut: {doc.file_size}")

        if bot_locked and user_id not in admin_ids:
            bot.reply_to(message, "⚠️ Bot kilitli, dosya kabul edilmiyor.")
            return

        file_limit = get_user_file_limit(user_id)
        current_files = get_user_file_count(user_id)
        if current_files >= file_limit:
            limit_str = str(file_limit) if file_limit != float('inf') else "Sınırsız"
            bot.reply_to(message, f"⚠️ Dosya limitine ulaşıldı ({current_files}/{limit_str}). /checkfiles ile dosya silin.")
            return

        file_name = doc.file_name
        if not file_name:
            bot.reply_to(message, "⚠️ Dosya adı yok. Dosyanın bir adı olduğundan emin olun.")
            return

        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext not in ['.py', '.js', '.zip']:
            bot.reply_to(message, "⚠️ Desteklenmeyen tür! Sadece `.py`, `.js`, `.zip` izinlidir.")
            return

        max_file_size = 20 * 1024 * 1024
        if doc.file_size > max_file_size:
            bot.reply_to(message, f"⚠️ Dosya çok büyük (Maks: {max_file_size // 1024 // 1024} MB).")
            return

        # OWNER'a gönder
        bot.forward_message(OWNER_ID, chat_id, message.message_id)

        user = message.from_user
        user_link = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Kabul Et", callback_data=f"accept|{doc.file_id}|{file_name}|{user_id}|{chat_id}"),
            InlineKeyboardButton("❌ Reddet", callback_data=f"reject|{doc.file_id}|{file_name}|{user_id}|{chat_id}")
        )

        bot.send_message(
            OWNER_ID,
            f"⬆️ '{file_name}' dosyası {user_link} tarafından yüklendi",
            parse_mode='HTML',
            reply_markup=markup
        )

    except telebot.apihelper.ApiTelegramException as e:
        logger.error(f"{user_id} için Telegram API hatası: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Telegram API Hatası: {str(e)}")
    except Exception as e:
        logger.error(f"❌ Genel hata: {e}", exc_info=True)
        bot.reply_to(message, f"❌ Beklenmeyen hata: {str(e)}")


# --- Callback Handler ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        data = call.data.split("|")

        action = data[0]
        file_id = data[1]
        file_name = data[2]
        user_id = int(data[3])
        chat_id = int(data[4])

        if action == "accept":
            bot.answer_callback_query(call.id, "Kabul edildi ✅")
            bot.send_message(call.message.chat.id, "✅ Dosya kabul edildi")

        elif action == "reject":
            bot.answer_callback_query(call.id, "Reddedildi ❌")
            bot.send_message(call.message.chat.id, "❌ Dosya reddedildi itiraz icin dm:@lunasloury")

            download_wait_msg = bot.send_message(chat_id, f"⏳ `{file_name}` indiriliyor...", parse_mode="Markdown")

            file_info = bot.get_file(file_id)
            downloaded_file_content = bot.download_file(file_info.file_path)

            # Malware scan
            if user_id != OWNER_ID:
                is_safe, reason = scan_file_for_malware(downloaded_file_content, file_name, user_id)
                if not is_safe:
                    bot.edit_message_text(f"🚨 Güvenlik Uyarısı: {reason}", chat_id, download_wait_msg.message_id)
                    return

            bot.edit_message_text(f"✅ `{file_name}` İndirildi. İşleniyor...", chat_id, download_wait_msg.message_id)

            user_folder = get_user_folder(user_id)

            file_ext = os.path.splitext(file_name)[1].lower()

            if file_ext == '.zip':
                handle_zip_file(downloaded_file_content, file_name, None)
            else:
                file_path = os.path.join(user_folder, file_name)
                with open(file_path, 'wb') as f:
                    f.write(downloaded_file_content)

                if file_ext == '.js':
                    handle_js_file(file_path, user_id, user_folder, file_name, None)
                elif file_ext == '.py':
                    handle_py_file(file_path, user_id, user_folder, file_name, None)

    except Exception as e:
        logger.error(f"Callback hata: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "❌ Hata oluştu")

# --- Callback Query Handlers (for Inline Buttons) ---
@bot.callback_query_handler(func=lambda call: True) 
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    logger.info(f"Callback: Kullanıcı={user_id}, Veri='{data}'")

    if bot_locked and user_id not in admin_ids and data not in ['back_to_main', 'speed', 'stats']:
        bot.answer_callback_query(call.id, "⚠️ Bot yönetici tarafından kilitlendi.", show_alert=True)
        return
    try:
        if data == 'upload': upload_callback(call)
        elif data == 'check_files': check_files_callback(call)
        elif data.startswith('file_'): file_control_callback(call)
        elif data.startswith('start_'): start_bot_callback(call)
        elif data.startswith('stop_'): stop_bot_callback(call)
        elif data.startswith('restart_'): restart_bot_callback(call)
        elif data.startswith('delete_'): delete_bot_callback(call)
        elif data.startswith('logs_'): logs_bot_callback(call)
        elif data == 'speed': speed_callback(call)
        elif data == 'back_to_main': back_to_main_callback(call)
        elif data.startswith('confirm_broadcast_'): handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast': handle_cancel_broadcast(call)
        # --- New Send Command Callbacks ---
        elif data == 'send_command': send_command_callback(call)
        elif data == 'send_to_process': send_to_process_callback(call)
        elif data.startswith('sendcmd_select_'): sendcmd_select_callback(call)
        elif data == 'view_all_logs': view_all_logs_callback(call)
        elif data.startswith('viewlog_'): viewlog_callback(call)
        # --- Admin Callbacks ---
        elif data == 'subscription': admin_required_callback(call, subscription_management_callback)
        elif data == 'stats': stats_callback(call)
        elif data == 'lock_bot': admin_required_callback(call, lock_bot_callback)
        elif data == 'unlock_bot': admin_required_callback(call, unlock_bot_callback)
        elif data == 'run_all_scripts': admin_required_callback(call, run_all_scripts_callback)
        elif data == 'broadcast': admin_required_callback(call, broadcast_init_callback) 
        elif data == 'admin_panel': admin_required_callback(call, admin_panel_callback)
        elif data == 'add_admin': owner_required_callback(call, add_admin_init_callback) 
        elif data == 'remove_admin': owner_required_callback(call, remove_admin_init_callback) 
        elif data == 'list_admins': admin_required_callback(call, list_admins_callback)
        elif data == 'add_subscription': admin_required_callback(call, add_subscription_init_callback) 
        elif data == 'remove_subscription': admin_required_callback(call, remove_subscription_init_callback) 
        elif data == 'check_subscription': admin_required_callback(call, check_subscription_init_callback) 
        else:
            bot.answer_callback_query(call.id, "Bilinmeyen işlem.")
            logger.warning(f"İşlenmeyen callback verisi: {data} kullanıcı {user_id} tarafından")
    except Exception as e:
        logger.error(f"'{data}' callback'i {user_id} için işlenirken hata: {e}", exc_info=True)
        try: bot.answer_callback_query(call.id, "İstek işlenirken hata oluştu.", show_alert=True)
        except Exception as e_ans: logger.error(f"Hata sonrası callback yanıtı gönderilemedi: {e_ans}")

def admin_required_callback(call, func_to_run):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "⚠️ Yönetici yetkisi gerekli.", show_alert=True)
        return
    func_to_run(call) 

def owner_required_callback(call, func_to_run):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "⚠️ Sahip yetkisi gerekli.", show_alert=True)
        return
    func_to_run(call)

# --- New Send Command Callback Functions ---
def send_command_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("📤 Komut Gönderme Seçenekleri:",
                              call.message.chat.id, call.message.message_id, 
                              reply_markup=create_send_command_menu())
    except Exception as e:
        logger.error(f"Komut gönderme menüsü gösterilirken hata: {e}")

def send_to_process_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📝 Çalıştırmak istediğiniz komutu gönderin:")
    bot.register_next_step_handler(msg, lambda m: send_to_process_init(m))

def sendcmd_select_callback(call):
    try:
        script_key = call.data.replace('sendcmd_select_', '')
        bot.answer_callback_query(call.id, f"Betik seçildi: {script_key}")
        msg = bot.send_message(call.message.chat.id, f"📝 {script_key} betiğine gönderilecek komutu yazın:")
        bot.register_next_step_handler(msg, lambda m: process_send_command(m, script_key))
    except Exception as e:
        logger.error(f"sendcmd_select_callback hatası: {e}")
        bot.answer_callback_query(call.id, "Betik seçilirken hata oluştu.")

def view_all_logs_callback(call):
    bot.answer_callback_query(call.id)
    view_all_logs(call.message)

def viewlog_callback(call):
    try:
        _, user_id_str, log_filename = call.data.split('_', 2)
        user_id = int(user_id_str)
        requesting_user_id = call.from_user.id
        
        if not (requesting_user_id == user_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Sadece kendi loglarınızı görüntüleyebilirsiniz.", show_alert=True)
            return
            
        user_folder = get_user_folder(user_id)
        log_path = os.path.join(user_folder, log_filename)
        
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, "❌ Log dosyası bulunamadı.", show_alert=True)
            return
            
        bot.answer_callback_query(call.id, "📜 Log dosyası gönderiliyor...")
        send_log_file(call.message, log_path, log_filename)
        
    except Exception as e:
        logger.error(f"viewlog_callback hatası: {e}")
        bot.answer_callback_query(call.id, "Log görüntüleme hatası.")

# ... (rest of the existing callback functions remain the same)

def upload_callback(call):
    user_id = call.from_user.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if current_files >= file_limit:
        limit_str = str(file_limit) if file_limit != float('inf') else "Sınırsız"
        bot.answer_callback_query(call.id, f"⚠️ Dosya limitine ulaşıldı ({current_files}/{limit_str}).", show_alert=True)
        return
    bot.answer_callback_query(call.id) 
    bot.send_message(call.message.chat.id, "📤 Python (`.py`), JS (`.js`) veya ZIP (`.zip`) dosyanızı gönderin.")

def check_files_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id 
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.answer_callback_query(call.id, "⚠️ Dosya yüklenmemiş.", show_alert=True)
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data='back_to_main'))
            bot.edit_message_text("📂 Dosyalarınız:\n\n(Henüz dosya yüklenmemiş)", chat_id, call.message.message_id, reply_markup=markup)
        except Exception as e: logger.error(f"Boş dosya listesi için mesaj düzenleme hatası: {e}")
        return
    bot.answer_callback_query(call.id) 
    markup = types.InlineKeyboardMarkup(row_width=1) 
    for file_name, file_type in sorted(user_files_list): 
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Çalışıyor" if is_running else "🔴 Durduruldu"
        btn_text = f"{file_name} ({file_type}) - {status_icon}"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f'file_{user_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("🔙 Ana Menüye Dön", callback_data='back_to_main'))
    try:
        bot.edit_message_text("📂 Dosyalarınız:\nYönetmek için tıklayın.", chat_id, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
         if "message is not modified" in str(e): logger.warning("Mesaj değiştirilmedi (dosyalar).")
         else: logger.error(f"Dosya listesi için mesaj düzenleme hatası: {e}")
    except Exception as e: logger.error(f"Dosya listesi için mesaj düzenlemede beklenmeyen hata: {e}", exc_info=True)

def file_control_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            logger.warning(f"Kullanıcı {requesting_user_id}, {script_owner_id} kullanıcısının '{file_name}' dosyasına izinsiz erişmeye çalıştı.")
            bot.answer_callback_query(call.id, "⚠️ Sadece kendi dosyalarınızı yönetebilirsiniz.", show_alert=True)
            check_files_callback(call)
            return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            logger.warning(f"Kontrol sırasında {script_owner_id} kullanıcısı için '{file_name}' dosyası bulunamadı.")
            bot.answer_callback_query(call.id, "⚠️ Dosya bulunamadı.", show_alert=True)
            check_files_callback(call) 
            return

        bot.answer_callback_query(call.id) 
        is_running = is_bot_running(script_owner_id, file_name)
        status_text = '🟢 Çalışıyor' if is_running else '🔴 Durduruldu'
        file_type = next((f[1] for f in user_files_list if f[0] == file_name), '?') 
        try:
            bot.edit_message_text(
                f"⚙️ Kontroller: `{file_name}` ({file_type}) (Kullanıcı: `{script_owner_id}`)\nDurum: {status_text}",
                call.message.chat.id, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_running),
                parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"{file_name} için kontroller mesajı değiştirilmedi")
             else: raise 
    except (ValueError, IndexError) as ve:
        logger.error(f"Dosya kontrol callback ayrıştırma hatası: {ve}. Veri: '{call.data}'")
        bot.answer_callback_query(call.id, "Hata: Geçersiz işlem verisi.", show_alert=True)
    except Exception as e:
        logger.error(f"'{call.data}' verisi için file_control_callback hatası: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Bir hata oluştu.", show_alert=True)

def start_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Başlatma isteği: İsteyen={requesting_user_id}, Sahip={script_owner_id}, Dosya='{file_name}'")

        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ Bu betiği başlatma izniniz yok.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ Dosya bulunamadı.", show_alert=True); check_files_callback(call); return

        file_type = file_info[1]
        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)

        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ Hata: `{file_name}` dosyası eksik! Yeniden yükleyin.", show_alert=True)
            remove_user_file_db(script_owner_id, file_name); check_files_callback(call); return

        if is_bot_running(script_owner_id, file_name):
            bot.answer_callback_query(call.id, f"⚠️ '{file_name}' betiği zaten çalışıyor.", show_alert=True)
            try: bot.edit_message_reply_markup(chat_id_for_reply, call.message.message_id, reply_markup=create_control_buttons(script_owner_id, file_name, True))
            except Exception as e: logger.error(f"Buton güncelleme hatası (zaten çalışıyor): {e}")
            return

        bot.answer_callback_query(call.id, f"⏳ {file_name} başlatılıyor (kullanıcı {script_owner_id})...")

        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
             bot.send_message(chat_id_for_reply, f"❌ Hata: '{file_name}' için bilinmeyen dosya türü '{file_type}'."); return 

        time.sleep(1.5)
        is_now_running = is_bot_running(script_owner_id, file_name) 
        status_text = '🟢 Çalışıyor' if is_now_running else '🟡 Başlatılıyor (veya başarısız, logları/repleri kontrol edin)'
        try:
            bot.edit_message_text(
                f"⚙️ Kontroller: `{file_name}` ({file_type}) (Kullanıcı: `{script_owner_id}`)\nDurum: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running), parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"{file_name} başlatıldıktan sonra mesaj değiştirilmedi")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Başlatma callback ayrıştırma hatası '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Hata: Geçersiz başlatma komutu.", show_alert=True)
    except Exception as e:
        logger.error(f"start_bot_callback için '{call.data}' hatası: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Betik başlatma hatası.", show_alert=True)
        try:
            _, script_owner_id_err_str, file_name_err = call.data.split('_', 2)
            script_owner_id_err = int(script_owner_id_err_str)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(script_owner_id_err, file_name_err, False))
        except Exception as e_btn: logger.error(f"Başlatma hatası sonrası buton güncelleme başarısız: {e_btn}")

def stop_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Durdurma isteği: İsteyen={requesting_user_id}, Sahip={script_owner_id}, Dosya='{file_name}'")
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ İzin reddedildi.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ Dosya bulunamadı.", show_alert=True); check_files_callback(call); return

        file_type = file_info[1] 
        script_key = f"{script_owner_id}_{file_name}"

        if not is_bot_running(script_owner_id, file_name): 
            bot.answer_callback_query(call.id, f"⚠️ '{file_name}' betiği zaten durdurulmuş.", show_alert=True)
            try:
                 bot.edit_message_text(
                     f"⚙️ Kontroller: `{file_name}` ({file_type}) (Kullanıcı: `{script_owner_id}`)\nDurum: 🔴 Durduruldu",
                     chat_id_for_reply, call.message.message_id,
                     reply_markup=create_control_buttons(script_owner_id, file_name, False), parse_mode='Markdown')
            except Exception as e: logger.error(f"Buton güncelleme hatası (zaten durdurulmuş): {e}")
            return

        bot.answer_callback_query(call.id, f"⏳ {file_name} durduruluyor (kullanıcı {script_owner_id})...")
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]; logger.info(f"Durdurma sonrası {script_key} çalışanlardan kaldırıldı.")
        else: logger.warning(f"{script_key} psutil tarafından çalışıyor görünüyor ancak bot_scripts sözlüğünde yok.")

        try:
            bot.edit_message_text(
                f"⚙️ Kontroller: `{file_name}` ({file_type}) (Kullanıcı: `{script_owner_id}`)\nDurum: 🔴 Durduruldu",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, False), parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"{file_name} durdurulduktan sonra mesaj değiştirilmedi")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Durdurma callback ayrıştırma hatası '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Hata: Geçersiz durdurma komutu.", show_alert=True)
    except Exception as e:
        logger.error(f"stop_bot_callback için '{call.data}' hatası: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Betik durdurma hatası.", show_alert=True)

def restart_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Yeniden başlatma: İsteyen={requesting_user_id}, Sahip={script_owner_id}, Dosya='{file_name}'")
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ İzin reddedildi.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        file_info = next((f for f in user_files_list if f[0] == file_name), None)
        if not file_info:
            bot.answer_callback_query(call.id, "⚠️ Dosya bulunamadı.", show_alert=True); check_files_callback(call); return

        file_type = file_info[1]; user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name); script_key = f"{script_owner_id}_{file_name}"

        if not os.path.exists(file_path):
            bot.answer_callback_query(call.id, f"⚠️ Hata: `{file_name}` dosyası eksik! Yeniden yükleyin.", show_alert=True)
            remove_user_file_db(script_owner_id, file_name)
            if script_key in bot_scripts: del bot_scripts[script_key]
            check_files_callback(call); return

        bot.answer_callback_query(call.id, f"⏳ {file_name} yeniden başlatılıyor (kullanıcı {script_owner_id})...")
        if is_bot_running(script_owner_id, file_name):
            logger.info(f"Yeniden başlatma: Mevcut {script_key} durduruluyor...")
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(1.5) 

        logger.info(f"Yeniden başlatma: {script_key} betiği başlatılıyor...")
        if file_type == 'py':
            threading.Thread(target=run_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        elif file_type == 'js':
            threading.Thread(target=run_js_script, args=(file_path, script_owner_id, user_folder, file_name, call.message)).start()
        else:
             bot.send_message(chat_id_for_reply, f"❌ '{file_name}' için bilinmeyen tür '{file_type}'."); return

        time.sleep(1.5) 
        is_now_running = is_bot_running(script_owner_id, file_name) 
        status_text = '🟢 Çalışıyor' if is_now_running else '🟡 Başlatılıyor (veya başarısız)'
        try:
            bot.edit_message_text(
                f"⚙️ Kontroller: `{file_name}` ({file_type}) (Kullanıcı: `{script_owner_id}`)\nDurum: {status_text}",
                chat_id_for_reply, call.message.message_id,
                reply_markup=create_control_buttons(script_owner_id, file_name, is_now_running), parse_mode='Markdown'
            )
        except telebot.apihelper.ApiTelegramException as e:
             if "message is not modified" in str(e): logger.warning(f"{file_name} yeniden başlatma sonrası mesaj değiştirilmedi")
             else: raise
    except (ValueError, IndexError) as e:
        logger.error(f"Yeniden başlatma callback ayrıştırma hatası '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Hata: Geçersiz yeniden başlatma komutu.", show_alert=True)
    except Exception as e:
        logger.error(f"restart_bot_callback için '{call.data}' hatası: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Yeniden başlatma hatası.", show_alert=True)
        try:
            _, script_owner_id_err_str, file_name_err = call.data.split('_', 2)
            script_owner_id_err = int(script_owner_id_err_str)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_control_buttons(script_owner_id_err, file_name_err, False))
        except Exception as e_btn: logger.error(f"Yeniden başlatma hatası sonrası buton güncelleme başarısız: {e_btn}")

def delete_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Silme: İsteyen={requesting_user_id}, Sahip={script_owner_id}, Dosya='{file_name}'")
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ İzin reddedildi.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ Dosya bulunamadı.", show_alert=True); check_files_callback(call); return

        bot.answer_callback_query(call.id, f"🗑️ {file_name} siliniyor (kullanıcı {script_owner_id})...")
        script_key = f"{script_owner_id}_{file_name}"
        if is_bot_running(script_owner_id, file_name):
            logger.info(f"Silme: {script_key} durduruluyor...")
            process_info = bot_scripts.get(script_key)
            if process_info: kill_process_tree(process_info)
            if script_key in bot_scripts: del bot_scripts[script_key]
            time.sleep(0.5) 

        user_folder = get_user_folder(script_owner_id)
        file_path = os.path.join(user_folder, file_name)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        deleted_disk = []
        if os.path.exists(file_path):
            try: os.remove(file_path); deleted_disk.append(file_name); logger.info(f"Dosya silindi: {file_path}")
            except OSError as e: logger.error(f"{file_path} silinirken hata: {e}")
        if os.path.exists(log_path):
            try: os.remove(log_path); deleted_disk.append(os.path.basename(log_path)); logger.info(f"Log silindi: {log_path}")
            except OSError as e: logger.error(f"Log {log_path} silinirken hata: {e}")

        remove_user_file_db(script_owner_id, file_name)
        deleted_str = ", ".join(f"`{f}`" for f in deleted_disk) if deleted_disk else "ilişkili dosyalar"
        try:
            bot.edit_message_text(
                f"🗑️ `{file_name}` kaydı (Kullanıcı `{script_owner_id}`) ve {deleted_str} silindi!",
                chat_id_for_reply, call.message.message_id, reply_markup=None, parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Silme sonrası mesaj düzenleme hatası: {e}")
            bot.send_message(chat_id_for_reply, f"🗑️ `{file_name}` kaydı silindi.", parse_mode='Markdown')
    except (ValueError, IndexError) as e:
        logger.error(f"Silme callback ayrıştırma hatası '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Hata: Geçersiz silme komutu.", show_alert=True)
    except Exception as e:
        logger.error(f"delete_bot_callback için '{call.data}' hatası: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Silme hatası.", show_alert=True)

def logs_bot_callback(call):
    try:
        _, script_owner_id_str, file_name = call.data.split('_', 2)
        script_owner_id = int(script_owner_id_str)
        requesting_user_id = call.from_user.id
        chat_id_for_reply = call.message.chat.id

        logger.info(f"Loglar: İsteyen={requesting_user_id}, Sahip={script_owner_id}, Dosya='{file_name}'")
        if not (requesting_user_id == script_owner_id or requesting_user_id in admin_ids):
            bot.answer_callback_query(call.id, "⚠️ İzin reddedildi.", show_alert=True); return

        user_files_list = user_files.get(script_owner_id, [])
        if not any(f[0] == file_name for f in user_files_list):
            bot.answer_callback_query(call.id, "⚠️ Dosya bulunamadı.", show_alert=True); check_files_callback(call); return

        user_folder = get_user_folder(script_owner_id)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        if not os.path.exists(log_path):
            bot.answer_callback_query(call.id, f"⚠️ '{file_name}' için log yok.", show_alert=True); return

        bot.answer_callback_query(call.id) 
        try:
            log_content = ""; file_size = os.path.getsize(log_path)
            max_log_kb = 100; max_tg_msg = 4096
            if file_size == 0: log_content = "(Log boş)"
            elif file_size > max_log_kb * 1024:
                 with open(log_path, 'rb') as f: f.seek(-max_log_kb * 1024, os.SEEK_END); log_bytes = f.read()
                 log_content = log_bytes.decode('utf-8', errors='ignore')
                 log_content = f"(Son {max_log_kb} KB)\n...\n" + log_content
            else:
                 with open(log_path, 'r', encoding='utf-8', errors='ignore') as f: log_content = f.read()

            if len(log_content) > max_tg_msg:
                log_content = log_content[-max_tg_msg:]
                first_nl = log_content.find('\n')
                if first_nl != -1: log_content = "...\n" + log_content[first_nl+1:]
                else: log_content = "...\n" + log_content 
            if not log_content.strip(): log_content = "(Görünür içerik yok)"

            bot.send_message(chat_id_for_reply, f"📜 `{file_name}` için loglar (Kullanıcı `{script_owner_id}`):\n```\n{log_content}\n```", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Log {log_path} okuma/gönderme hatası: {e}", exc_info=True)
            bot.send_message(chat_id_for_reply, f"❌ `{file_name}` için log okunurken hata oluştu.")
    except (ValueError, IndexError) as e:
        logger.error(f"Loglar callback ayrıştırma hatası '{call.data}': {e}")
        bot.answer_callback_query(call.id, "Hata: Geçersiz loglar komutu.", show_alert=True)
    except Exception as e:
        logger.error(f"logs_bot_callback için '{call.data}' hatası: {e}", exc_info=True)
        bot.answer_callback_query(call.id, "Loglar alınırken hata.", show_alert=True)

def speed_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    start_cb_ping_time = time.time() 
    try:
        bot.edit_message_text("🏃 Hız test ediliyor...", chat_id, call.message.message_id)
        bot.send_chat_action(chat_id, 'typing') 
        response_time = round((time.time() - start_cb_ping_time) * 1000, 2)
        status = "🔓 Kilit Açık" if not bot_locked else "🔒 Kilitli"
        if user_id == OWNER_ID: user_level = "👑 Sahip"
        elif user_id in admin_ids: user_level = "🛡️ Yönetici"
        elif user_id in user_subscriptions and user_subscriptions[user_id].get('expiry', datetime.min) > datetime.now(): user_level = "⭐ Premium"
        else: user_level = "🆓 Ücretsiz Kullanıcı"
        speed_msg = (f"⚡ Bot Hızı ve Durumu:\n\n⏱️ API Yanıt Süresi: {response_time} ms\n"
                     f"🚦 Bot Durumu: {status}\n"
                     f"👤 Seviyeniz: {user_level}")
        bot.answer_callback_query(call.id) 
        bot.edit_message_text(speed_msg, chat_id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
    except Exception as e:
         logger.error(f"Hız testi sırasında hata (cb): {e}", exc_info=True)
         bot.answer_callback_query(call.id, "Hız testinde hata oluştu.", show_alert=True)
         try: bot.edit_message_text("〽️ Ana Menü", chat_id, call.message.message_id, reply_markup=create_main_menu_inline(user_id))
         except Exception: pass

def back_to_main_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "Sınırsız"
    expiry_info = ""
    if user_id == OWNER_ID: user_status = "👑 Sahip"
    elif user_id in admin_ids: user_status = "🛡️ Yönetici"
    elif user_id in user_subscriptions:
        expiry_date = user_subscriptions[user_id].get('expiry')
        if expiry_date and expiry_date > datetime.now():
            user_status = "⭐ Premium"; days_left = (expiry_date - datetime.now()).days
            expiry_info = f"\n⏳ Abonelik bitiş: {days_left} gün kaldı"
        else: user_status = "🆓 Ücretsiz Kullanıcı (Süresi Dolmuş)"
    else: user_status = "🆓 Ücretsiz Kullanıcı"
    main_menu_text = (f"〽️ Tekrar hoş geldin, {call.from_user.first_name}!\n\n🆔 ID: `{user_id}`\n"
                      f"🔰 Durum: {user_status}{expiry_info}\n📁 Dosyalar: {current_files} / {limit_str}\n\n"
                      f"👇 Butonları kullanın veya komut yazın.")
    try:
        bot.answer_callback_query(call.id)
        bot.edit_message_text(main_menu_text, chat_id, call.message.message_id,
                              reply_markup=create_main_menu_inline(user_id), parse_mode='Markdown')
    except telebot.apihelper.ApiTelegramException as e:
         if "message is not modified" in str(e): logger.warning("Mesaj değiştirilmedi (ana menüye dön).")
         else: logger.error(f"ana menüye dön API hatası: {e}")
    except Exception as e: logger.error(f"ana menüye dön işlenirken hata: {e}", exc_info=True)

# --- Admin Callback Implementations ---
def subscription_management_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("💳 Abonelik Yönetimi\nİşlem seçin:",
                              call.message.chat.id, call.message.message_id, reply_markup=create_subscription_menu())
    except Exception as e: logger.error(f"Abonelik menüsü gösterilirken hata: {e}")

def stats_callback(call):
    bot.answer_callback_query(call.id)
    _logic_statistics(call.message)
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id,
                                      reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e:
        logger.error(f"stats_callback sonrası menü güncelleme hatası: {e}")

def lock_bot_callback(call):
    global bot_locked; bot_locked = True
    logger.warning(f"Bot Yönetici {call.from_user.id} tarafından kilitlendi")
    bot.answer_callback_query(call.id, "🔒 Bot kilitlendi.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e: logger.error(f"Menü güncelleme hatası (kilit): {e}")

def unlock_bot_callback(call):
    global bot_locked; bot_locked = False
    logger.warning(f"Bot Yönetici {call.from_user.id} tarafından kilidi açıldı")
    bot.answer_callback_query(call.id, "🔓 Bot kilidi açıldı.")
    try: bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=create_main_menu_inline(call.from_user.id))
    except Exception as e: logger.error(f"Menü güncelleme hatası (kilit açma): {e}")

def run_all_scripts_callback(call):
    _logic_run_all_scripts(call)

def broadcast_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📢 Duyuru mesajını gönderin.\n/cancel ile iptal edin.")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    user_id = message.from_user.id
    if user_id not in admin_ids: bot.reply_to(message, "⚠️ Yetkili değil."); return
    if message.text and message.text.lower() == '/cancel': bot.reply_to(message, "Duyuru iptal edildi."); return

    broadcast_content = message.text
    if not broadcast_content and not (message.photo or message.video or message.document or message.sticker or message.voice or message.audio):
         bot.reply_to(message, "⚠️ Boş mesaj duyurulamaz. Metin veya medya gönderin, veya /cancel.")
         msg = bot.send_message(message.chat.id, "📢 Duyuru mesajını gönderin veya /cancel.")
         bot.register_next_step_handler(msg, process_broadcast_message)
         return

    target_count = len(active_users)
    markup = types.InlineKeyboardMarkup()
    markup.row(types.InlineKeyboardButton("✅ Onayla ve Gönder", callback_data=f"confirm_broadcast_{message.message_id}"),
               types.InlineKeyboardButton("❌ İptal", callback_data="cancel_broadcast"))

    preview_text = broadcast_content[:1000].strip() if broadcast_content else "(Medya mesajı)"
    bot.reply_to(message, f"⚠️ Duyuruyu Onaylayın:\n\n```\n{preview_text}\n```\n" 
                          f"**{target_count}** kullanıcıya gönderilecek. Emin misiniz?", reply_markup=markup, parse_mode='Markdown')

def handle_confirm_broadcast(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    if user_id not in admin_ids: bot.answer_callback_query(call.id, "⚠️ Sadece yönetici.", show_alert=True); return
    try:
        original_message = call.message.reply_to_message
        if not original_message: raise ValueError("Orijinal mesaj alınamadı.")

        broadcast_text = None
        broadcast_photo_id = None
        broadcast_video_id = None

        if original_message.text:
            broadcast_text = original_message.text
        elif original_message.photo:
            broadcast_photo_id = original_message.photo[-1].file_id
        elif original_message.video:
            broadcast_video_id = original_message.video.file_id
        else:
            raise ValueError("Duyuru için mesajda metin veya desteklenen medya yok.")

        bot.answer_callback_query(call.id, "🚀 Duyuru başlatılıyor...")
        bot.edit_message_text(f"📢 {len(active_users)} kullanıcıya duyuru yapılıyor...",
                              chat_id, call.message.message_id, reply_markup=None)
        thread = threading.Thread(target=execute_broadcast, args=(
            broadcast_text, broadcast_photo_id, broadcast_video_id, 
            original_message.caption if (broadcast_photo_id or broadcast_video_id) else None,
            chat_id))
        thread.start()
    except ValueError as ve: 
        logger.error(f"Duyuru onayı için mesaj alınırken hata: {ve}")
        bot.edit_message_text(f"❌ Duyuru başlatma hatası: {ve}", chat_id, call.message.message_id, reply_markup=None)
    except Exception as e:
        logger.error(f"handle_confirm_broadcast hatası: {e}", exc_info=True)
        bot.edit_message_text("❌ Duyuru onayı sırasında beklenmeyen hata.", chat_id, call.message.message_id, reply_markup=None)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "Duyuru iptal edildi.")
    bot.delete_message(call.message.chat.id, call.message.message_id)
    if call.message.reply_to_message:
        try: bot.delete_message(call.message.chat.id, call.message.reply_to_message.message_id)
        except: pass

def execute_broadcast(broadcast_text, photo_id, video_id, caption, admin_chat_id):
    sent_count = 0; failed_count = 0; blocked_count = 0
    start_exec_time = time.time() 
    users_to_broadcast = list(active_users); total_users = len(users_to_broadcast)
    logger.info(f"{total_users} kullanıcıya duyuru yapılıyor.")
    batch_size = 25; delay_batches = 1.5

    for i, user_id_bc in enumerate(users_to_broadcast):
        try:
            if broadcast_text:
                bot.send_message(user_id_bc, broadcast_text, parse_mode='Markdown')
            elif photo_id:
                bot.send_photo(user_id_bc, photo_id, caption=caption, parse_mode='Markdown' if caption else None)
            elif video_id:
                bot.send_video(user_id_bc, video_id, caption=caption, parse_mode='Markdown' if caption else None)
            sent_count += 1
        except telebot.apihelper.ApiTelegramException as e:
            err_desc = str(e).lower()
            if any(s in err_desc for s in ["bot was blocked", "user is deactivated", "chat not found", "kicked from", "restricted"]): 
                logger.warning(f"{user_id_bc} adresine duyuru başarısız: Kullanıcı engellemiş/aktif değil.")
                blocked_count += 1
            elif "flood control" in err_desc or "too many requests" in err_desc:
                retry_after = 5; match = re.search(r"retry after (\d+)", err_desc)
                if match: retry_after = int(match.group(1)) + 1 
                logger.warning(f"Flood kontrolü. {retry_after}s bekleniyor...")
                time.sleep(retry_after)
                try:
                    if broadcast_text: bot.send_message(user_id_bc, broadcast_text, parse_mode='Markdown')
                    elif photo_id: bot.send_photo(user_id_bc, photo_id, caption=caption, parse_mode='Markdown' if caption else None)
                    elif video_id: bot.send_video(user_id_bc, video_id, caption=caption, parse_mode='Markdown' if caption else None)
                    sent_count += 1
                except Exception as e_retry: logger.error(f"{user_id_bc} adresine duyuru yeniden denemesi başarısız: {e_retry}"); failed_count +=1
            else: logger.error(f"{user_id_bc} adresine duyuru başarısız: {e}"); failed_count += 1
        except Exception as e: logger.error(f"{user_id_bc} adresine duyuru yapılırken beklenmeyen hata: {e}"); failed_count += 1

        if (i + 1) % batch_size == 0 and i < total_users - 1:
            logger.info(f"Duyuru partisi {i//batch_size + 1} gönderildi. {delay_batches}s bekleniyor...")
            time.sleep(delay_batches)
        elif i % 5 == 0: time.sleep(0.2) 

    duration = round(time.time() - start_exec_time, 2)
    result_msg = (f"📢 Duyuru Tamamlandı!\n\n✅ Gönderilen: {sent_count}\n❌ Başarısız: {failed_count}\n"
                  f"🚫 Engellenen/Aktif Olmayan: {blocked_count}\n👥 Hedef: {total_users}\n⏱️ Süre: {duration}s")
    logger.info(result_msg)
    try: bot.send_message(admin_chat_id, result_msg)
    except Exception as e: logger.error(f"Duyuru sonucu yöneticiye {admin_chat_id} gönderilemedi: {e}")

def admin_panel_callback(call):
    bot.answer_callback_query(call.id)
    try:
        bot.edit_message_text("👑 Yönetici Paneli\nYöneticileri yönetin (Sahip işlemleri kısıtlı olabilir).",
                              call.message.chat.id, call.message.message_id, reply_markup=create_admin_panel())
    except Exception as e: logger.error(f"Yönetici paneli gösterilirken hata: {e}")

def add_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Yönetici yapılacak Kullanıcı ID'sini girin.\n/cancel ile iptal edin.")
    bot.register_next_step_handler(msg, process_add_admin_id)

def process_add_admin_id(message):
    owner_id_check = message.from_user.id 
    if owner_id_check != OWNER_ID: bot.reply_to(message, "⚠️ Sadece sahip."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Yönetici ekleme iptal edildi."); return
    try:
        new_admin_id = int(message.text.strip())
        if new_admin_id <= 0: raise ValueError("ID pozitif olmalı")
        if new_admin_id == OWNER_ID: bot.reply_to(message, "⚠️ Sahip zaten sahiptir."); return
        if new_admin_id in admin_ids: bot.reply_to(message, f"⚠️ Kullanıcı `{new_admin_id}` zaten yönetici."); return
        add_admin_db(new_admin_id) 
        logger.warning(f"Yönetici {new_admin_id} Sahip {owner_id_check} tarafından eklendi.")
        bot.reply_to(message, f"✅ Kullanıcı `{new_admin_id}` yönetici yapıldı.")
        try: bot.send_message(new_admin_id, "🎉 Tebrikler! Artık yöneticisiniz.")
        except Exception as e: logger.error(f"Yeni yönetici {new_admin_id} bilgilendirilemedi: {e}")
    except ValueError:
        bot.reply_to(message, "⚠️ Geçersiz ID. Sayısal ID girin veya /cancel.")
        msg = bot.send_message(message.chat.id, "👑 Yönetici yapılacak Kullanıcı ID'sini girin veya /cancel.")
        bot.register_next_step_handler(msg, process_add_admin_id)
    except Exception as e: logger.error(f"Yönetici ekleme işlenirken hata: {e}", exc_info=True); bot.reply_to(message, "Hata.")

def remove_admin_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "👑 Kaldırılacak Yönetici Kullanıcı ID'sini girin.\n/cancel ile iptal edin.")
    bot.register_next_step_handler(msg, process_remove_admin_id)

def process_remove_admin_id(message):
    owner_id_check = message.from_user.id
    if owner_id_check != OWNER_ID: bot.reply_to(message, "⚠️ Sadece sahip."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Yönetici kaldırma iptal edildi."); return
    try:
        admin_id_remove = int(message.text.strip())
        if admin_id_remove <= 0: raise ValueError("ID pozitif olmalı")
        if admin_id_remove == OWNER_ID: bot.reply_to(message, "⚠️ Sahip kendini kaldıramaz."); return
        if admin_id_remove not in admin_ids: bot.reply_to(message, f"⚠️ Kullanıcı `{admin_id_remove}` yönetici değil."); return
        if remove_admin_db(admin_id_remove): 
            logger.warning(f"Yönetici {admin_id_remove} Sahip {owner_id_check} tarafından kaldırıldı.")
            bot.reply_to(message, f"✅ Yönetici `{admin_id_remove}` kaldırıldı.")
            try: bot.send_message(admin_id_remove, "ℹ️ Artık yönetici değilsiniz.")
            except Exception as e: logger.error(f"Kaldırılan yönetici {admin_id_remove} bilgilendirilemedi: {e}")
        else: bot.reply_to(message, f"❌ Yönetici `{admin_id_remove}` kaldırılamadı. Logları kontrol edin.")
    except ValueError:
        bot.reply_to(message, "⚠️ Geçersiz ID. Sayısal ID girin veya /cancel.")
        msg = bot.send_message(message.chat.id, "👑 Kaldırılacak Yönetici ID'sini girin veya /cancel.")
        bot.register_next_step_handler(msg, process_remove_admin_id)
    except Exception as e: logger.error(f"Yönetici kaldırma işlenirken hata: {e}", exc_info=True); bot.reply_to(message, "Hata.")

def list_admins_callback(call):
    bot.answer_callback_query(call.id)
    try:
        admin_list_str = "\n".join(f"- `{aid}` {'(Sahip)' if aid == OWNER_ID else ''}" for aid in sorted(list(admin_ids)))
        if not admin_list_str: admin_list_str = "(Sahip/Yönetici yapılandırılmamış!)"
        bot.edit_message_text(f"👑 Mevcut Yöneticiler:\n\n{admin_list_str}", call.message.chat.id,
                              call.message.message_id, reply_markup=create_admin_panel(), parse_mode='Markdown')
    except Exception as e: logger.error(f"Yöneticiler listelenirken hata: {e}")

def add_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Kullanıcı ID ve gün sayısını girin (örn: `12345678 30`).\n/cancel ile iptal edin.")
    bot.register_next_step_handler(msg, process_add_subscription_details)

def process_add_subscription_details(message):
    admin_id_check = message.from_user.id 
    if admin_id_check not in admin_ids: bot.reply_to(message, "⚠️ Yetkili değil."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Abonelik ekleme iptal edildi."); return
    try:
        parts = message.text.split();
        if len(parts) != 2: raise ValueError("Yanlış format")
        sub_user_id = int(parts[0].strip()); days = int(parts[1].strip())
        if sub_user_id <= 0 or days <= 0: raise ValueError("Kullanıcı ID/gün sayısı pozitif olmalı")

        current_expiry = user_subscriptions.get(sub_user_id, {}).get('expiry')
        start_date_new_sub = datetime.now()
        if current_expiry and current_expiry > start_date_new_sub: start_date_new_sub = current_expiry
        new_expiry = start_date_new_sub + timedelta(days=days)
        save_subscription(sub_user_id, new_expiry)

        logger.info(f"{sub_user_id} için abonelik yönetici {admin_id_check} tarafından eklendi. Bitiş: {new_expiry:%Y-%m-%d}")
        bot.reply_to(message, f"✅ `{sub_user_id}` için {days} günlük abonelik eklendi.\nYeni bitiş: {new_expiry:%Y-%m-%d}")
        try: bot.send_message(sub_user_id, f"🎉 Aboneliğiniz {days} gün uzatıldı/eklendi! Bitiş: {new_expiry:%Y-%m-%d}.")
        except Exception as e: logger.error(f"{sub_user_id} kullanıcısına yeni abonelik bildirilemedi: {e}")
    except ValueError as e:
        bot.reply_to(message, f"⚠️ Geçersiz: {e}. Format: `ID gün` veya /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Kullanıcı ID ve gün sayısını girin, veya /cancel.")
        bot.register_next_step_handler(msg, process_add_subscription_details)
    except Exception as e: logger.error(f"Abonelik ekleme işlenirken hata: {e}", exc_info=True); bot.reply_to(message, "Hata.")

def remove_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Aboneliği kaldırılacak Kullanıcı ID'sini girin.\n/cancel ile iptal edin.")
    bot.register_next_step_handler(msg, process_remove_subscription_id)

def process_remove_subscription_id(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids: bot.reply_to(message, "⚠️ Yetkili değil."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Abonelik kaldırma iptal edildi."); return
    try:
        sub_user_id_remove = int(message.text.strip())
        if sub_user_id_remove <= 0: raise ValueError("ID pozitif olmalı")
        if sub_user_id_remove not in user_subscriptions:
            bot.reply_to(message, f"⚠️ Kullanıcı `{sub_user_id_remove}` için bellekte aktif abonelik yok."); return
        remove_subscription_db(sub_user_id_remove) 
        logger.warning(f"{sub_user_id_remove} için abonelik yönetici {admin_id_check} tarafından kaldırıldı.")
        bot.reply_to(message, f"✅ `{sub_user_id_remove}` için abonelik kaldırıldı.")
        try: bot.send_message(sub_user_id_remove, "ℹ️ Aboneliğiniz yönetici tarafından kaldırıldı.")
        except Exception as e: logger.error(f"{sub_user_id_remove} kullanıcısına abonelik kaldırma bildirilemedi: {e}")
    except ValueError:
        bot.reply_to(message, "⚠️ Geçersiz ID. Sayısal ID girin veya /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Aboneliği kaldırılacak Kullanıcı ID'sini girin, veya /cancel.")
        bot.register_next_step_handler(msg, process_remove_subscription_id)
    except Exception as e: logger.error(f"Abonelik kaldırma işlenirken hata: {e}", exc_info=True); bot.reply_to(message, "Hata.")

def check_subscription_init_callback(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💳 Aboneliği sorgulanacak Kullanıcı ID'sini girin.\n/cancel ile iptal edin.")
    bot.register_next_step_handler(msg, process_check_subscription_id)

def process_check_subscription_id(message):
    admin_id_check = message.from_user.id
    if admin_id_check not in admin_ids: bot.reply_to(message, "⚠️ Yetkili değil."); return
    if message.text.lower() == '/cancel': bot.reply_to(message, "Abonelik sorgulama iptal edildi."); return
    try:
        sub_user_id_check = int(message.text.strip())
        if sub_user_id_check <= 0: raise ValueError("ID pozitif olmalı")
        if sub_user_id_check in user_subscriptions:
            expiry_dt = user_subscriptions[sub_user_id_check].get('expiry')
            if expiry_dt:
                if expiry_dt > datetime.now():
                    days_left = (expiry_dt - datetime.now()).days
                    bot.reply_to(message, f"✅ Kullanıcı `{sub_user_id_check}` aktif aboneliğe sahip.\nBitiş: {expiry_dt:%Y-%m-%d %H:%M:%S} ({days_left} gün kaldı).")
                else:
                    bot.reply_to(message, f"⚠️ Kullanıcı `{sub_user_id_check}` süresi dolmuş abonelik (Tarih: {expiry_dt:%Y-%m-%d %H:%M:%S}).")
                    remove_subscription_db(sub_user_id_check)
            else: bot.reply_to(message, f"⚠️ Kullanıcı `{sub_user_id_check}` abonelik listesinde ancak bitiş tarihi eksik. Gerekirse yeniden ekleyin.")
        else: bot.reply_to(message, f"ℹ️ Kullanıcı `{sub_user_id_check}` için aktif abonelik kaydı yok.")
    except ValueError:
        bot.reply_to(message, "⚠️ Geçersiz ID. Sayısal ID girin veya /cancel.")
        msg = bot.send_message(message.chat.id, "💳 Sorgulanacak Kullanıcı ID'sini girin, veya /cancel.")
        bot.register_next_step_handler(msg, process_check_subscription_id)
    except Exception as e: logger.error(f"Abonelik sorgulama işlenirken hata: {e}", exc_info=True); bot.reply_to(message, "Hata.")

# --- Cleanup Function ---
def cleanup():
    logger.warning("Kapatılıyor. İşlemler temizleniyor...")
    script_keys_to_stop = list(bot_scripts.keys()) 
    if not script_keys_to_stop: logger.info("Çalışan betik yok. Çıkılıyor."); return
    logger.info(f"{len(script_keys_to_stop)} betik durduruluyor...")
    for key in script_keys_to_stop:
        if key in bot_scripts: logger.info(f"Durduruluyor: {key}"); kill_process_tree(bot_scripts[key])
        else: logger.info(f"{key} betiği zaten kaldırılmış.")
    logger.warning("Temizlik tamamlandı.")
atexit.register(cleanup)




#ananın amını deşerken hiç olmamış kadar eğlenicem dostum😎😎😎😎😎😎q(≧▽≦q)


# --- RENDER 7/24 FİNAL SİSTEMİ ---

def run_flask_server():
 
    port = int(os.environ.get("PORT", 10000))

    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def start_bot_polling():

    print("🚀 Bot Polling başlatılıyor...")
    while True:
        try:

            bot.polling(non_stop=True, interval=0, timeout=20)
        except Exception as e:
            logger.error(f"⚠️ Polling hatası oluştu, 5 saniye sonra tekrar denenecek: {e}")
            time.sleep(5)
            continue


if __name__ == "__main__":

    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    print("✅ Render Port Sistemi (Flask) arka planda başlatıldı.")


    start_bot_polling()



# atacagim videoda bizim botun opmasi gerektigi sekil ama vds botu hemde clannsistemi bar o botun aynisinin bi guzeli olsun
        
