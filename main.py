import os
import sqlite3
import io
import threading
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          ConversationHandler, MessageHandler, filters)

# --- إعدادات الخطوط (التعديلات المعتمدة) ---
# المراجع:
FONT_FILE = "arial.ttf"
TITLE_SIZE = 65
TEXT_SIZE = 50
HEADER_SIZE = 80
CELL_SIZE = 70

# --- إعداد Flask (للإبقاء على البوت يعمل على السيرفرات) ---
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "البوت يعمل بكامل طاقته!"

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- قاعدة البيانات ---
conn = sqlite3.connect('league.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY, team1 TEXT, team2 TEXT, s1 INTEGER DEFAULT 0, s2 INTEGER DEFAULT 0, round_num INTEGER, played INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS laws (id INTEGER PRIMARY KEY, content TEXT)''')
conn.commit()

# --- محرك الرسم الذكي ---
def get_font(size):
    try: return ImageFont.truetype(FONT_FILE, size)
    except: return ImageFont.load_default()

def draw_text_smart(draw, x, y, text, font, color, align_right=True):
    reshaped = arabic_reshaper.reshape(text)
    bidi = get_display(reshaped)
    bbox = draw.textbbox((0, 0), bidi, font=font)
    w = bbox[2] - bbox[0]
    pos_x = (x - w) if align_right else x
    draw.text((pos_x, y), bidi, font=font, fill=color)

def create_table_image(data):
    w, h = 2500, 700 + (len(data) * 250)
    img = Image.new('RGB', (w, h), color='#0F172A')
    draw = ImageDraw.Draw(img)
    headers = ["النقاط", "لعب", "فوز", "تعادل", "خسارة", "أهداف", "الفريق"]
    draw.rectangle([0, 0, w, 250], fill="#1E293B")
    
    # Header
    for i, h_text in enumerate(headers):
        draw_text_smart(draw, 2300 - (i*300), 50, h_text, get_font(HEADER_SIZE), "#F59E0B", True)
    
    y = 350
    for idx, row in enumerate(data):
        bg = "#16213e" if idx % 2 == 0 else "#0F172A"
        draw.rectangle([0, y-20, w, y+200], fill=bg)
        draw_text_smart(draw, 2300, y, str(row[0]), get_font(CELL_SIZE), "white", True)
        for i in range(1, 7):
            draw_text_smart(draw, 2000 - (i*300), y, str(row[i]), get_font(CELL_SIZE), "#38BDF8", False)
        y += 250
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return buf

# --- منطق الأوامر ---
COUNT, TEAM = range(2)

async def setup_entry(u, c):
    # تحقق من وجود دوري حالي
    cursor.execute("SELECT count(*) FROM matches")
    if cursor.fetchone()[0] > 0:
        kb = [[InlineKeyboardButton("✅ نعم، احذف", callback_data='confirm_setup')], 
              [InlineKeyboardButton("❌ لا", callback_data='cancel_setup')]]
        await u.message.reply_text("⚠️ يوجد دوري حالي. سيتم حذف البيانات؟", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
    await u.message.reply_text("كم عدد الفرق؟ (يجب أن يكون زوجياً)"); return COUNT

async def table_cmd(u, c):
    cursor.execute("SELECT name FROM teams"); teams = [r[0] for r in cursor.fetchall()]
    # تعديل: عرض الجدول حتى لو كانت المباريات صفر
    stats = {t: {'j':0, 'g':0, 'n':0, 'p':0, 'b':0, 'pts':0} for t in teams}
    cursor.execute("SELECT team1, team2, s1, s2 FROM matches WHERE played=1")
    for t1, t2, s1, s2 in cursor.fetchall():
        stats[t1]['j']+=1; stats[t2]['j']+=1; stats[t1]['b']+=s1; stats[t2]['b']+=s2
        if s1>s2: stats[t1]['g']+=1; stats[t1]['pts']+=3; stats[t2]['p']+=1
        elif s2>s1: stats[t2]['g']+=1; stats[t2]['pts']+=3; stats[t1]['p']+=1
        else: stats[t1]['n']+=1; stats[t1]['pts']+=1; stats[t2]['n']+=1; stats[t2]['pts']+=1
    
    data = [[t, st['j'], st['g'], st['n'], st['p'], st['b'], st['pts']] for t, st in stats.items()]
    data.sort(key=lambda x: (x[6], x[5]), reverse=True)
    await u.message.reply_photo(photo=create_table_image(data))

# --- التشغيل ---
if __name__ == '__main__':
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    threading.Thread(target=run_web).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # (إضافة الهاندلرز)
    app.add_handler(CommandHandler("setup", setup_entry))
    app.add_handler(CommandHandler("table", table_cmd))
    # أضف باقي الهاندلرز بنفس الطريقة
    app.run_polling()
