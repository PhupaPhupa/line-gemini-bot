import os
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
import google.generativeai as genai

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# กำหนด Keywords สำหรับข้าม AI
KEYWORDS = [
    "FAQ", "faq", "Faq", "คำถามที่พบบ่อย", "คำถาม",
    "Instruction", "instruction", "INSTRUCTION", "คู่มือ", "วิธีใช้งาน", "แนะนำการใช้งาน",
    "About Me", "about me", "About me", "ABOUT ME", "เกี่ยวกับเรา", "เกี่ยวกับฉัน",
    "AWD", "awd", "Awd"
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

    # ตรวจสอบว่ามี Keyword คำไหนอยู่ในข้อความผู้ใช้หรือไม่ (แปลงเป็นพิมพ์เล็กเพื่อเทียบได้ง่ายขึ้น)
    user_text_lower = user_text.lower()
    if any(kw.lower() in user_text_lower for kw in KEYWORDS):
        return  # ถ้าเจอ Keyword ให้หยุดทำงาน เพื่อปล่อยให้ LINE OA Auto-response ตอบแทน

    # ถ้าไม่พบ Keyword ใดๆ ให้ Gemini AI ประมวลผลและตอบกลับ
    response = model.generate_content(user_text)
    ai_reply = response.text

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=ai_reply)]
            )
        )

if __name__ == "__main__":
    app.run(port=5000)
