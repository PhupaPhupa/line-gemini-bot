import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from google import genai

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ตั้งชื่อโมเดลผ่าน env ได้ ไม่ต้องแก้โค้ดทุกครั้ง
# gemini-2.5-flash-lite มักมีโควต้าฟรีสูงสุด ถ้าไม่ชัวร์ให้ลิสต์ดูด้วย client.models.list()
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')

client = genai.Client(api_key=GEMINI_API_KEY)

system_instruction = """
คุณคือผู้ช่วย AI ของโครงการ SMART AWD METHANE ROVER
หน้าที่ของคุณคือตอบคำถามผู้ใช้เกี่ยวกับระบบตรวจวัดก๊าซมีเทนและสภาพแวดล้อมแปลงนา
หากผู้ใช้ถามขอลิงก์เว็บ ให้ส่งลิงก์ http://ac54241.assumptiondev.com/methanetast/index.html ให้ผู้ใช้
ตอบด้วยภาษาไทยที่สุภาพ เป็นกันเอง และสั้นกระชับ
"""

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ข้อความที่ต้องการให้ LINE OA ตอบเอง (เช็กแบบตรงทั้งข้อความ)
KEYWORDS = {
    "faq", "คำถามที่พบบ่อย",
    "instruction", "คู่มือ",
    "about me", "เกี่ยวกับเรา",
    "awd",
}

FALLBACK_MSG = "ขออภัยครับ ระบบกำลังประมวลผลหนาแน่น ลองใหม่อีกครั้งนะครับ"


def reply_text(reply_token, text):
    text = text[:4900]  # LINE จำกัด 5,000 ตัวอักษร
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )


@app.route("/webhook", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text.strip()

    # ถ้าตรงกับ keyword ให้ LINE OA ตอบเอง
    if user_text.lower() in KEYWORDS:
        return

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_text,
            config={'system_instruction': system_instruction}
        )
        ai_reply = (response.text or "").strip() or FALLBACK_MSG
        reply_text(event.reply_token, ai_reply)

    except Exception as e:
        # ถ้าเจอ 429 แปลว่าโควต้าฟรีเต็ม
        print(f"Gemini Error: {e}")
        try:
            reply_text(event.reply_token, FALLBACK_MSG)
        except Exception as inner_e:
            print(f"Line Reply Error: {inner_e}")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
