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

KEYWORDS = [
    "FAQ", "faq", "Faq", "คำถามที่พบบ่อย",
    "Instruction", "instruction", "คู่มือ", "แนะนำการใช้งาน",
    "About Me", "about me", "เกี่ยวกับเรา", "เกี่ยวกับฉัน",
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

    # ตรวจสอบว่าตรงกับ Keyword หรือไม่
    user_text_lower = user_text.lower()
    if any(kw.lower() in user_text_lower for kw in KEYWORDS):
        return  # ปล่อยให้ LINE OA Auto-response ตอบแทน

    # ถ้าไม่ตรงกับ Keyword ส่งให้ Gemini AI ตอบ
    try:
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
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    app.run(port=5000)
