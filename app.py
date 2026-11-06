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
from google.genai import types

app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# ตั้งชื่อโมเดลผ่าน env ได้ ไม่ต้องแก้โค้ดทุกครั้ง
# ถ้าไม่ชัวร์ว่าชื่อไหนใช้ได้ ให้ลิสต์ดูด้วย client.models.list()
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')

client = genai.Client(api_key=GEMINI_API_KEY)


def load_knowledge():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge.txt')
    try:
        with open(path, encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print("ไม่พบไฟล์ knowledge.txt")
        return ""


KNOWLEDGE = load_knowledge()

system_instruction = f"""
คุณคือผู้ช่วย AI ของโครงการ SMART AWD METHANE ROVER
ตอบคำถามเกี่ยวกับโครงการ ระบบตรวจวัดก๊าซมีเทน การทำนาข้าว การจัดการน้ำแบบ AWD คาร์บอนเครดิต และเรื่องที่เกี่ยวข้อง

ลำดับการตอบ:
1. คำถามเกี่ยวกับตัวโครงการ (อุปกรณ์ งบ เป้าหมาย วิธีทำงาน) ให้ตอบจาก "ข้อมูลโครงการ" ด้านล่าง
2. คำถามความรู้ทั่วไป (เช่น ช่วงไหนของการทำนาปล่อยมีเทนมาก ข้าวพันธุ์ไหนปล่อยน้อย คาร์บอนเครดิตทำอย่างไร) ซึ่งข้อมูลโครงการไม่ได้ระบุ ให้ใช้เครื่องมือ Google Search ค้นหาทุกครั้ง แล้วสรุปคำตอบ
3. ห้ามตอบว่า "ในข้อมูลโครงการไม่มี" แล้วจบ ต้องค้นหาและตอบให้ได้ก่อนเสมอ
4. เมื่อตอบจากการค้นเว็บ ให้ขึ้นต้นว่า "จากการค้นข้อมูลเพิ่มเติม" และห้ามแต่งตัวเลขเอง
5. บอกว่าไม่พบข้อมูล เฉพาะกรณีที่ค้นแล้วจริงๆ ไม่เจอแหล่งที่เชื่อถือได้
6. หากผู้ใช้ขอลิงก์เว็บ ให้ส่งลิงก์ Dashboard ในข้อมูลโครงการ
7. ตอบภาษาไทย สุภาพ เป็นกันเอง สั้นกระชับ (ไม่เกิน 5-6 บรรทัด ยกเว้นผู้ใช้ขอรายละเอียด)
8. ไม่ใช้สัญลักษณ์ markdown เช่น ** หรือ # เพราะ LINE แสดงไม่ได้

===== ข้อมูลโครงการ =====
{KNOWLEDGE}
"""

# config แบบเปิดการค้นเว็บ (Google Search grounding)
CONFIG_WITH_SEARCH = types.GenerateContentConfig(
    system_instruction=system_instruction,
    tools=[types.Tool(google_search=types.GoogleSearch())],
)

# config สำรอง ไม่ค้นเว็บ (ใช้เมื่อค้นเว็บไม่ได้ เช่น โควต้าค้นหาเต็ม)
CONFIG_NO_SEARCH = types.GenerateContentConfig(
    system_instruction=system_instruction,
)

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


def ask_gemini(user_text):
    """ถามแบบมีค้นเว็บก่อน ถ้าพังให้ลองใหม่แบบไม่ค้นเว็บ"""
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_text,
            config=CONFIG_WITH_SEARCH,
        )
        text = (response.text or "").strip()
        if text:
            return text
    except Exception as e:
        print(f"Gemini (with search) Error: {e}")

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_text,
        config=CONFIG_NO_SEARCH,
    )
    return (response.text or "").strip()


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
        ai_reply = ask_gemini(user_text) or FALLBACK_MSG
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
