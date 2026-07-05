import os
import asyncio
import threading
from flask import Flask

# استيراد الدوال من ملفاتك
# ملاحظة: يجب أن تكون هذه الدوال موجودة ومعرفة داخل ملفاتك
from bot_service import run_service
from bot_test import run_test

# --- سيرفر Flask (لإبقاء البوت مستيقظاً على Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "جميع البوتات تعمل بنجاح!"

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- التشغيل المتزامن للبوتات ---
async def main():
    # سحب التوكنات من إعدادات Render بأمان
    token_service = os.environ.get("TOKEN_SERVICE")
    token_test = os.environ.get("TOKEN_TEST")

    if not token_service or not token_test:
        print("⚠️ خطأ: تأكد من إضافة TOKEN_SERVICE و TOKEN_TEST في إعدادات البيئة (Environment Variables) في Render")
        return

    print("🚀 بدء تشغيل البوتات...")

    # تشغيل البوتات معاً في نفس الوقت
    await asyncio.gather(
        asyncio.to_thread(run_service, token_service),
        asyncio.to_thread(run_test, token_test)
    )

if __name__ == '__main__':
    # تشغيل السيرفر في خلفية (Thread)
    threading.Thread(target=run_web).start()
    
    # تشغيل البوتات
    asyncio.run(main())
