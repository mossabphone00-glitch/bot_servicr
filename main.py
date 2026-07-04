import os, sqlite3, io, threading
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
                          ConversationHandler, MessageHandler, filters)

# --- الإعدادات ---
ADMIN_ID = 8642841625 # <--- ضع رقم الـ ID الخاص بك هنا
BOT_TOKEN = os.environ.get("BOT_TOKEN")
FONT_FILE = "arial.ttf"

# --- قاعدة البيانات ---
conn = sqlite3.connect('league.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS teams (name TEXT PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY, team1 TEXT, team2 TEXT, s1 INTEGER DEFAULT 0, s2 INTEGER DEFAULT 0, round_num INTEGER, played INTEGER DEFAULT 0)''')
conn.commit()

# --- دالة الخط (مع فحص وجود الملف) ---
def get_font(size):
    if os.path.exists(FONT_FILE):
        return ImageFont.truetype(FONT_FILE, size)
    else:
        print(f"تحذير: ملف {FONT_FILE} غير موجود! سيتم استخدام الخط الافتراضي.")
        return ImageFont.load_default()

def draw_text_arabic(draw, pos, text, font, color):
    reshaped = arabic_reshaper.reshape(text)
    bidi = get_display(reshaped)
    draw.text(pos, bidi, font=font, fill=color)

# --- الدوال الفنية ---
def create_table_image(data):
    w, h = 2500, 700 + (len(data) * 250)
    img = Image.new('RGB', (w, h), color='#1a1a2e')
    draw = ImageDraw.Draw(img)
    header_font = get_font(120)
    cell_font = get_font(100)
    
    headers = ["TEAM", "MP", "W", "D", "L", "B", "Pts"]
    draw.rectangle([0, 0, w, 250], fill="#2C3E50")
    for i, h_text in enumerate(headers):
        pos_x = 100 if i == 0 else 800 + (i-1)*250
        draw.text((pos_x, 50), h_text, fill="#E74C3C", font=header_font)

    y = 350
    for idx, row in enumerate(data):
        bg = "#16213e" if idx % 2 == 0 else "#1a1a2e"
        draw.rectangle([0, y-20, w, y+200], fill=bg)
        draw_text_arabic(draw, (100, y), str(row[0]), cell_font, "white")
        for i in range(1, 7):
            draw.text((800 + (i-1)*250, y), str(row[i]), fill="#f8f9fa", font=cell_font)
        y += 250
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return buf

def create_fixture_image(round_num, matches):
    w, h = 1800, 500 + (len(matches) * 250)
    img = Image.new('RGB', (w, h), color='#1a1a2e')
    draw = ImageDraw.Draw(img)
    title_font, text_font = get_font(100), get_font(80)

    draw.text((600, 50), f"Journée {round_num}", fill="#f8b400", font=title_font)
    y = 250
    for m in matches:
        draw.rectangle([50, y, 1750, y+200], fill="#16213e", outline="#e94560", width=6)
        draw_text_arabic(draw, (100, y+50), m[0], text_font, "white")
        draw.text((800, y+50), "VS", fill="#e94560", font=text_font)
        draw_text_arabic(draw, (1200, y+50), m[1], text_font, "white")
        y += 250
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return buf

# --- منطق الأوامر ---
COUNT, TEAM = range(2)

async def is_admin(u):
    if u.effective_user.id != ADMIN_ID:
        await u.message.reply_text("⛔ غير مسموح."); return False
    return True

async def setup_entry(u, c):
    if not await is_admin(u): return
    cursor.execute("SELECT count(*) FROM matches")
    if cursor.fetchone()[0] > 0:
        kb = [[InlineKeyboardButton("✅ نعم، احذف", callback_data='confirm_setup')], [InlineKeyboardButton("❌ لا", callback_data='cancel_setup')]]
        await u.message.reply_text("⚠️ يوجد دوري حالي. سيتم مسحه؟", reply_markup=InlineKeyboardMarkup(kb))
        return
    await u.message.reply_text("كم عدد الفرق؟"); return COUNT

async def count_h(u, c):
    c.user_data['count'] = int(u.message.text); c.user_data['teams'] = []
    await u.message.reply_text("اسم الفريق 1:"); return TEAM

async def team_h(u, c):
    teams = c.user_data.get('teams', []); teams.append(u.message.text.strip())
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
    conn.commit(); await u.message.reply_text("✅ تم!"); return ConversationHandler.END

async def table_cmd(u, c):
    cursor.execute("SELECT name FROM teams"); teams = [r[0] for r in cursor.fetchall()]
    if not teams: await u.message.reply_text("الدوري فارغ."); return
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
    cursor.execute("SELECT MIN(round_num) FROM matches WHERE played=0")
    res = cursor.fetchone()
    if not res or res[0] is None: await u.message.reply_text("انتهى الدوري!"); return
    cursor.execute("SELECT team1, team2 FROM matches WHERE round_num=? AND played=0", (res[0],))
    await u.message.reply_photo(photo=create_fixture_image(res[0], cursor.fetchall()))

async def add_res_init(u, c):
    if not await is_admin(u): return
    if len(c.args) != 4: await u.message.reply_text("استخدم: /add الفريق1 2 الفريق2 1"); return
    c.user_data['m'] = {'t1': c.args[0], 's1': c.args[1], 't2': c.args[2], 's2': c.args[3]}
    kb = [[InlineKeyboardButton("✅ تأكيد", callback_data='ok'), InlineKeyboardButton("❌ إلغاء", callback_data='no')]]
    await u.message.reply_text(f"تأكيد: {c.args[0]} {c.args[1]} - {c.args[3]} {c.args[2]}", reply_markup=InlineKeyboardMarkup(kb))

async def btn_h(u, c):
    q = u.callback_query
    await q.answer() # رد على الزر لإخفاء علامة التحميل
    data = q.data

    # --- التعامل مع أزرار إضافة النتيجة ---
    if data == 'ok':
        m = c.user_data.get('m')
        cursor.execute("UPDATE matches SET s1=?, s2=?, played=1 WHERE team1=? AND team2=? AND played=0", (m['s1'], m['s2'], m['t1'], m['t2']))
        conn.commit(); await q.edit_message_text("✅ تم الحفظ!")
    
    elif data == 'no':
        await q.edit_message_text("🚫 تم الإلغاء.")

    # --- التعامل مع أزرار التحذير (setup) ---
    elif data == 'confirm_setup':
        cursor.execute("DELETE FROM matches")
        cursor.execute("DELETE FROM teams")
        conn.commit()
        await q.edit_message_text("✅ تم مسح الدوري القديم. يرجى كتابة /setup مجدداً للبدء.")
        
    elif data == 'cancel_setup':
        await q.edit_message_text("🚫 تم إلغاء عملية المسح.")


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    conv = ConversationHandler(entry_points=[CommandHandler('setup', setup_entry)], states={COUNT:[MessageHandler(filters.TEXT, count_h)], TEAM:[MessageHandler(filters.TEXT, team_h)]}, fallbacks=[])
    app.add_handler(conv); app.add_handler(CommandHandler("table", table_cmd)); app.add_handler(CommandHandler("round", round_cmd)); app.add_handler(CommandHandler("add", add_res_init)); app.add_handler(CallbackQueryHandler(btn_h))
    app.run_polling()
