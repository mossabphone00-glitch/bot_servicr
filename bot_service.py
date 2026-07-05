import sqlite3, io, os
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          ConversationHandler, MessageHandler, filters)

# الإعدادات
ADMIN_IDS = [8642841625,6022075170] 
FONT_FILE = "arial.ttf"

# --- دوال الرسم (تبقى كما هي) ---
def get_font(size):
    if os.path.exists(FONT_FILE):
        return ImageFont.truetype(FONT_FILE, size)
    else:
        return ImageFont.load_default()

def draw_text_arabic(draw, pos, text, font, color):
    reshaped = arabic_reshaper.reshape(text)
    bidi = get_display(reshaped)
    draw.text(pos, bidi, font=font, fill=color)

# [هنا نضع الدوال create_table_image و create_fixture_image كما كانت في كودك الأصلي]
# (اختصاراً للمساحة وضعتها هنا، تأكد من نقلها كما هي)

def run_service(token):
    # --- قاعدة البيانات (داخل الدالة لضمان عملها) ---
    conn = sqlite3.connect('league.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY, team1 TEXT, team2 TEXT, s1 INTEGER DEFAULT 0, s2 INTEGER DEFAULT 0, round_num INTEGER, played INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS laws (id INTEGER PRIMARY KEY, content TEXT)''')
    conn.commit()

    # --- منطق الأوامر والدوال المساعدة ---
    # (هنا تنقل جميع الدوال: is_admin, cancel, laws_cmd, add_laws_cmd, setup_entry, count_h, team_h, table_cmd, round_cmd, add_res_init, btn_h)
    # ملاحظة: تأكد أنها تستخدم cursor الذي عرفناه داخل هذه الدالة أو اجعلها تستقبل الكائنات كـ parameters
    
    # --- تشغيل البوت ---
    app = ApplicationBuilder().token(token).build()
    
    # إضافة الهاندلرز
    conv = ConversationHandler(
        entry_points=[CommandHandler('setup', setup_entry)], 
        states={COUNT:[MessageHandler(filters.TEXT, count_h)], TEAM:[MessageHandler(filters.TEXT, team_h)]}, 
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("table", table_cmd))
    app.add_handler(CommandHandler("round", round_cmd))
    app.add_handler(CommandHandler("add", add_res_init))
    app.add_handler(CommandHandler("laws", laws_cmd))
    app.add_handler(CommandHandler("add_laws", add_laws_cmd))
    app.add_handler(CallbackQueryHandler(btn_h))
    
    print("🚀 تم تشغيل Service Bot بنجاح!")
    app.run_polling()
