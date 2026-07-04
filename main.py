import os, sqlite3, io, threading
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          ConversationHandler, MessageHandler, filters)

# --- إعدادات الألوان الفنية ---
BG_COLOR = "#0F172A"      # أزرق ليلي عميق
CARD_COLOR = "#1E293B"    # لون البطاقات/الصفوف
ACCENT_COLOR = "#F59E0B"  # ذهبي للعناوين
TEXT_COLOR = "#F8FAFC"    # أبيض ناصع
SEC_COLOR = "#38BDF8"     # سماوي للأرقام

app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "البوت يعمل بكامل طاقته!"

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app_web.run(host='0.0.0.0', port=port)

ADMIN_IDS = [8642841625] 
BOT_TOKEN = os.environ.get("BOT_TOKEN")
FONT_FILE = "arial.ttf"

# قاعدة البيانات
conn = sqlite3.connect('league.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY, team1 TEXT, team2 TEXT, s1 INTEGER DEFAULT 0, s2 INTEGER DEFAULT 0, round_num INTEGER, played INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS laws (id INTEGER PRIMARY KEY, content TEXT)''')
conn.commit()

# --- محرك الرسم الذكي ---
def get_font(size):
    return ImageFont.truetype(FONT_FILE, size) if os.path.exists(FONT_FILE) else ImageFont.load_default()

def draw_text_right_aligned(draw, x_limit, y, text, font, color, is_arabic=True):
    # معالجة النص
    if is_arabic:
        text = get_display(arabic_reshaper.reshape(text))
    
    # حساب العرض للقيام بالمحاذاة
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    
    # الرسم بدءاً من الحد اليميني مطروحاً منه عرض النص
    draw.text((x_limit - w, y), text, font=font, fill=color)

def wrap_text(text, font, max_width):
    lines = []
    for paragraph in text.split('\n'):
        words = paragraph.split(' ')
        line = ""
        for word in words:
            test_line = line + word + " "
            bbox = font.getbbox(test_line)
            if bbox[2] - bbox[0] < max_width: line = test_line
            else:
                lines.append(line); line = word + " "
        lines.append(line)
    return lines

# --- الصور ---
def create_laws_image(text):
    w, h = 1600, 2000
    img = Image.new('RGB', (w, h), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_text_right_aligned(draw, 1400, 50, "📜 قوانين الدوري", get_font(100), ACCENT_COLOR, True)
    y = 250
    for line in wrap_text(text, get_font(65), 1400):
        draw_text_right_aligned(draw, 1500, y, line, get_font(65), TEXT_COLOR, True)
        y += 85
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return buf

def create_table_image(data):
    w, h = 2500, 700 + (len(data) * 250)
    img = Image.new('RGB', (w, h), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    # الهيدرز
    headers = ["النقاط", "لعب", "فوز", "تعادل", "خسارة", "أهداف", "الفريق"]
    for i, h_text in enumerate(headers):
        draw_text_right_aligned(draw, 2300 - (i*350), 50, h_text, get_font(120), ACCENT_COLOR, True)
    
    y = 350
    for idx, row in enumerate(data):
        draw.rectangle([0, y-20, w, y+200], fill=CARD_COLOR)
        # اسم الفريق
        draw_text_right_aligned(draw, 2300, y, str(row[0]), get_font(100), TEXT_COLOR, True)
        # الأرقام
        for i in range(1, 7):
            draw_text_right_aligned(draw, 2000 - (i*350), y, str(row[i]), get_font(100), SEC_COLOR, False)
        y += 250
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return buf

def create_fixture_image(round_num, matches):
    w, h = 1800, 500 + (len(matches) * 250)
    img = Image.new('RGB', (w, h), color=BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_text_right_aligned(draw, 1600, 50, f"الجولة {round_num}", get_font(100), ACCENT_COLOR, True)
    
    y = 250
    for m in matches:
        draw.rectangle([50, y, 1750, y+200], fill=CARD_COLOR, outline=ACCENT_COLOR, width=4)
        draw_text_right_aligned(draw, 1700, y+50, m[1], get_font(80), TEXT_COLOR, True) # فريق 2
        draw_text_right_aligned(draw, 950, y+50, "VS", get_font(80), ACCENT_COLOR, False)
        draw_text_right_aligned(draw, 700, y+50, m[0], get_font(80), TEXT_COLOR, True) # فريق 1
        y += 250
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return buf

# --- منطق الأوامر ---
COUNT, TEAM = range(2)
async def is_admin(u): 
    if u.effective_user.id not in ADMIN_IDS: await u.message.reply_text("⛔ غير مسموح."); return False
    return True

async def cancel(u, c): await u.message.reply_text("تم الإلغاء."); c.user_data.clear(); return ConversationHandler.END

async def laws_cmd(u, c):
    cursor.execute("SELECT content FROM laws"); res = cursor.fetchone()
    if not res: await u.message.reply_text("لا قوانين."); return
    await u.message.reply_photo(photo=create_laws_image(res[0]))

async def add_laws_cmd(u, c):
    if not await is_admin(u): return
    if len(u.message.text.split(' ', 1)) < 2: return
    new_laws = u.message.text.split(' ', 1)[1]
    cursor.execute("DELETE FROM laws"); cursor.execute("INSERT INTO laws (content) VALUES (?)", (new_laws,)); conn.commit()
    await u.message.reply_text("✅ تم تحديث القوانين.")

async def setup_entry(u, c):
    if not await is_admin(u): return
    cursor.execute("SELECT count(*) FROM matches")
    if cursor.fetchone()[0] > 0:
        kb = [[InlineKeyboardButton("✅ نعم", callback_data='confirm_setup')], [InlineKeyboardButton("❌ لا", callback_data='cancel_setup')]]
        await u.message.reply_text("⚠️ يوجد دوري حالي. هل نحذفه؟", reply_markup=InlineKeyboardMarkup(kb)); return
    await u.message.reply_text("كم عدد الفرق؟"); return COUNT

async def count_h(u, c):
    try:
        count = int(u.message.text)
        if count % 2 != 0: await u.message.reply_text("يجب أن يكون زوجياً."); return COUNT
        c.user_data['count'] = count; c.user_data['teams'] = []; await u.message.reply_text("اسم الفريق 1:"); return TEAM
    except: return COUNT

async def team_h(u, c):
    name = u.message.text.strip(); teams = c.user_data.get('teams', [])
    teams.append(name)
    if len(teams) < c.user_data['count']: await u.message.reply_text(f"اسم الفريق {len(teams)+1}:"); return TEAM
    cursor.execute("DELETE FROM teams"); cursor.execute("DELETE FROM matches")
    for t in teams: cursor.execute("INSERT INTO teams VALUES (?)", (t,))
    n = len(teams); rounds = []; fixed = teams[0]; rotating = teams[1:]
    for r in range(n-1):
        rnd = []; cur = [fixed] + rotating
        for i in range(n//2): rnd.append((cur[i], cur[n-1-i]))
        rounds.append(rnd); rotating = [rotating[-1]] + rotating[:-1]
    for i, r_matches in enumerate(rounds):
        for m in r_matches: cursor.execute("INSERT INTO matches (team1, team2, round_num) VALUES (?,?,?)", (m[0], m[1], i+1))
    conn.commit(); await u.message.reply_text("✅ تم إنشاء الدوري!"); return ConversationHandler.END

async def table_cmd(u, c):
    cursor.execute("SELECT name FROM teams"); teams = [r[0] for r in cursor.fetchall()]
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

async def round_cmd(u, c):
    cursor.execute("SELECT MIN(round_num) FROM matches WHERE played=0"); res = cursor.fetchone()
    if not res or res[0] is None: await u.message.reply_text("انتهى الدوري!"); return
    cursor.execute("SELECT team1, team2 FROM matches WHERE round_num=? AND played=0", (res[0],))
    await u.message.reply_photo(photo=create_fixture_image(res[0], cursor.fetchall()))

async def add_res_init(u, c):
    if not await is_admin(u): return
    if len(c.args) != 4: return
    c.user_data['m'] = {'t1': c.args[0], 's1': c.args[1], 't2': c.args[2], 's2': c.args[3]}
    kb = [[InlineKeyboardButton("✅ تأكيد", callback_data='ok'), InlineKeyboardButton("❌ إلغاء", callback_data='no')]]
    await u.message.reply_text(f"تأكيد: {c.args[0]} {c.args[1]} - {c.args[3]} {c.args[2]}", reply_markup=InlineKeyboardMarkup(kb))

async def btn_h(u, c):
    q = u.callback_query; await q.answer(); data = q.data
    if data == 'ok':
        m = c.user_data.get('m')
        cursor.execute("UPDATE matches SET s1=?, s2=?, played=1 WHERE team1=? AND team2=? AND played=0", (m['s1'], m['s2'], m['t1'], m['t2']))
        conn.commit(); await q.edit_message_text("✅ تم الحفظ!")
    elif data == 'confirm_setup':
        cursor.execute("DELETE FROM matches"); cursor.execute("DELETE FROM teams"); conn.commit()
        await q.edit_message_text("✅ تم المسح.")
    else: await q.edit_message_text("🚫 أُلغيت.")

if __name__ == '__main__':
    threading.Thread(target=run_web).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    # (بقية الإعدادات كما هي..)
    conv = ConversationHandler(entry_points=[CommandHandler('setup', setup_entry)], states={COUNT:[MessageHandler(filters.TEXT, count_h)], TEAM:[MessageHandler(filters.TEXT, team_h)]}, fallbacks=[CommandHandler('cancel', cancel)])
    app.add_handler(conv); app.add_handler(CommandHandler("table", table_cmd)); app.add_handler(CommandHandler("round", round_cmd))
    app.add_handler(CommandHandler("add", add_res_init)); app.add_handler(CommandHandler("laws", laws_cmd)); app.add_handler(CommandHandler("add_laws", add_laws_cmd)); app.add_handler(CallbackQueryHandler(btn_h))
    app.run_polling()
