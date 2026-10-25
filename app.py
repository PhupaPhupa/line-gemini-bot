import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from google import genai  # ใช้แพ็กเกจใหม่ล่าสุด

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ตั้งค่า Gemini AI Client แบบใหม่
client = genai.Client(api_key=GEMINI_API_KEY)

# กำหนดบทบาทและข้อมูลให้ Gemini AI (System Instruction)
system_instruction = """
คุณคือผู้ช่วย AI ของโครงการ SMART AWD METHANE ROVER
หน้าที่ของคุณคือตอบคำถามผู้ใช้เกี่ยวกับระบบตรวจวัดก๊าซมีเทนและสภาพแวดล้อมแปลงนา
หากผู้ใช้ถามขอลิงก์เว็บ ให้ส่งลิงก์ http://ac54241.assumptiondev.com/methanetast/index.html ให้ผู้ใช้
ตอบด้วยภาษาไทยที่สุภาพ เป็นกันเอง และสั้นกระชับ
"""

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# คีย์เวิร์ดที่ต้องการให้ LINE OA ตอบเอง (ไม่ผ่าน Gemini)
KEYWORDS = [
    "FAQ", "faq", "คำถามที่พบบ่อย",
    "Instruction", "instruction", "คู่มือ",
    "About Me", "about me", "เกี่ยวกับเรา",
    "AWD", "awd"
]

@app.route("/webhook", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_text = event.message.text.strip()

    # ตรวจสอบ Keyword
    user_text_lower = user_text.lower()
    if any(kw.lower() in user_text_lower for kw in KEYWORDS):
        return  # ปล่อยให้ LINE OA ตอบเอง

    # ส่งให้ Gemini AI ประมวลผลด้วย SDK ตัวใหม่ พร้อมระบบป้องกันล่ม
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=user_text,
            config={
                'system_instruction': system_instruction
            }
        )
        ai_reply = response.text.strip()

        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=ai_reply)]
                )
            )
    except Exception as e:
        print(f"Gemini Error: {e}")
        # กรณีเกิด Error ส่งข้อความแจ้งเตือนผู้ใช้แทนที่จะปล่อยให้บอทนิ่งเงียบหรือพัง
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="ขออภัยครับ ระบบกำลังประมวลผลหนาแน่น ลองใหม่อีกครั้งนะครับ")]
                    )
                )
        except Exception as inner_e:
            print(f"Line Reply Error: {inner_e}")

if __name__ == "__main__":
    app.run(port=5000)
