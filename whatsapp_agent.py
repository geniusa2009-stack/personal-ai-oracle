"""
whatsapp_agent.py — موديول الرد الآلي على واتساب
WhatsApp Automation Module — built on the OFFICIAL WhatsApp Cloud API (Meta).

لماذا الـ Cloud API الرسمي؟ لأن الأدوات غير الرسمية (التي تتحكم في تطبيق واتساب)
تخالف شروط الخدمة وقد تؤدي إلى حظر رقمك. هذا الموديول آمن ومستدام.

أوضاع التشغيل (متغيّر البيئة WA_AUTO_REPLY):
  - "draft"  (افتراضي) → يكتب رداً ذكياً ويخزّنه كمسودّة لتراجعه وتوافق عليه من التطبيق.
  - "send"            → يرد تلقائياً فوراً (استخدمه بحذر).

متغيّرات البيئة المطلوبة للإرسال:
  WA_VERIFY_TOKEN     رمز تحقق الويبهوك (تختاره أنت)
  WA_ACCESS_TOKEN     توكن الوصول من Meta
  WA_PHONE_NUMBER_ID  معرّف رقم الواتساب من Meta
  OPENROUTER_API_KEY  لتوليد الردود

التشغيل المحلي:   python whatsapp_agent.py
الإنتاج (gunicorn): gunicorn "whatsapp_agent:create_app()" --bind 0.0.0.0:$PORT
"""

import os
import json

import requests

import db
import database
from scholarship_expert import is_scholarship_query, answer_scholarship_query

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GRAPH_API_VERSION = os.environ.get("WA_GRAPH_VERSION", "v20.0")

# --------------------------------------------------------------------------
# 1) System Prompt — خبير ثقافة مصرية يرد بعامية طبيعية حسب علاقة المرسل
# --------------------------------------------------------------------------
RELATIONSHIP_STYLE = {
    "friend":  "صاحبك القريب — هزار خفيف، ودّ، وعفوية. تقدر تستخدم إيموچي بسيط.",
    "family":  "قريب/عيلة — دفء واحترام وحنية، بدون رسمية تقيلة.",
    "work":    "زميل/شغل — محترم وودود ومختصر، بدون تكلّف.",
    "group":   "جروب أصحاب — خفيف ومرح وسريع، ومتدخلش في تفاصيل كتير.",
    "formal":  "شخص رسمي — مؤدب ومهني وواضح، عامية مهذّبة.",
}


def build_system_prompt(contact: dict) -> str:
    rel = (contact or {}).get("relationship", "friend")
    name = (contact or {}).get("name", "")
    notes = (contact or {}).get("notes", "")
    style = RELATIONSHIP_STYLE.get(rel, RELATIONSHIP_STYLE["friend"])
    extra = f"\nملاحظات عن الشخص: {notes}" if notes else ""
    return (
        "إنت مساعد بترد على رسائل واتساب نيابةً عن صاحب الحساب، وبتتكلم باللهجة المصرية "
        "العامية الطبيعية جداً زي ابن البلد الذكي — مش رسمي ولا متكلّف، وبتفهم السياق "
        "والثقافة المصرية (الهزار، المجاملات، التحيات، المناسبات).\n"
        f"طبيعة العلاقة مع المرسِل: {style}{extra}\n"
        f"اسم المرسِل (لو معروف): {name}\n"
        "قواعد مهمة:\n"
        "- رد قصير وطبيعي زي ما حد مصري بيكتب فعلاً، من غير مبالغة في الإيموچي.\n"
        "- لو السؤال محتاج معلومة مش متأكد منها، رد بصراحة واقترح إنه يراجع صاحب الحساب.\n"
        "- متوعدش بحاجات نيابة عن صاحب الحساب (مواعيد/فلوس) من غير ما توضّح إنها محتاجة تأكيد.\n"
        "- لو الرسالة فيها كلام حسّاس أو خصوصي، خليك متحفّظ واقترح الرد الشخصي."
    )


def _headers(api_key):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def generate_reply(text: str, contact: dict, history: list = None) -> str:
    """يولّد رداً ذكياً بالعامية. يراعي ذاكرة المحادثة، ولو السؤال عن المنح يدمج خبير المنح."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    if not key:
        return ""

    # توجيه ذكي: لو الرسالة عن منح → استعن بخبير المنح
    scholarship_ctx = ""
    if is_scholarship_query(text):
        info = answer_scholarship_query(text, use_web=bool(os.environ.get("OPENROUTER_API_KEY")))
        scholarship_ctx = f"\n\n[معلومات من خبير المنح لتلخيصها بالعامية للمرسل]:\n{info}"

    # ذاكرة المحادثة السابقة (من جدول whatsapp_chats)
    memory_ctx = ""
    if history:
        lines = [f"المرسِل: {h.get('incoming_message','')}\nانت: {h.get('smart_reply','')}"
                 for h in history if h.get("incoming_message")]
        if lines:
            memory_ctx = "سياق المحادثة السابقة (للاستمرارية):\n" + "\n".join(lines) + "\n\n"

    system = build_system_prompt(contact)
    user = (f"{memory_ctx}رسالة جديدة وصلتلك من المرسِل:\n«{text}»{scholarship_ctx}"
            f"\n\nاكتب الرد المناسب بالعامية.")
    try:
        r = requests.post(
            OPENROUTER_URL, headers=_headers(key),
            data=json.dumps({"model": model, "temperature": 0.8,
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user}]}),
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(تعذّر توليد الرد: {e})"


# --------------------------------------------------------------------------
# 2) الإرسال عبر Cloud API
# --------------------------------------------------------------------------
def send_whatsapp_message(to_wa_id: str, body: str) -> dict:
    token = os.environ.get("WA_ACCESS_TOKEN", "")
    phone_id = os.environ.get("WA_PHONE_NUMBER_ID", "")
    if not token or not phone_id:
        return {"ok": False, "error": "WA_ACCESS_TOKEN / WA_PHONE_NUMBER_ID غير مضبوطين"}
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_id}/messages"
    payload = {"messaging_product": "whatsapp", "to": to_wa_id,
               "type": "text", "text": {"body": body}}
    try:
        r = requests.post(url, headers=_headers(token), data=json.dumps(payload), timeout=30)
        r.raise_for_status()
        return {"ok": True, "response": r.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def approve_and_send(message_id: int, wa_id: str, body: str) -> dict:
    """يُستخدم من واجهة التطبيق للموافقة على مسودّة وإرسالها."""
    result = send_whatsapp_message(wa_id, body)
    db.set_message_status(message_id, "sent" if result["ok"] else "failed")
    if result["ok"]:
        db.log_wa_message(wa_id, "out", body, "sent")
    return result


# --------------------------------------------------------------------------
# 3) معالجة الرسائل الواردة
# --------------------------------------------------------------------------
def extract_messages(payload: dict) -> list:
    """يستخرج الرسائل النصية من حمولة ويبهوك واتساب. قابل للاختبار بدون شبكة."""
    out = []
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = {c.get("wa_id"): c.get("profile", {}).get("name")
                            for c in value.get("contacts", [])}
                for msg in value.get("messages", []):
                    if msg.get("type") != "text":
                        continue
                    wa_id = msg.get("from", "")
                    out.append({
                        "wa_id": wa_id,
                        "name": contacts.get(wa_id),
                        "text": msg.get("text", {}).get("body", ""),
                    })
    except Exception:
        return out
    return out


def handle_incoming(payload: dict) -> list:
    """يعالج كل رسالة واردة: يسجّل، يولّد رداً، ويرسل أو يحفظ كمسودّة حسب الوضع."""
    db.init_db()
    database.init_database()
    mode = os.environ.get("WA_AUTO_REPLY", "draft").lower()
    actions = []
    for m in extract_messages(payload):
        wa_id, text = m["wa_id"], m["text"]
        if not wa_id or not text:
            continue
        contact = db.upsert_contact(wa_id, m.get("name"))
        db.log_wa_message(wa_id, "in", text, "received")
        # قمع المبيعات: لو الرسالة فيها نية شراء، استخدم رد البيع التلقائي
        reply = None
        try:
            import income_hunter
            if income_hunter.is_buyer_intent(text):
                reply = income_hunter.sales_funnel_reply(text)
        except Exception:
            reply = None
        # وإلا رد عادي بالعامية مع ذاكرة المحادثة
        if not reply:
            history = database.get_chat_history(wa_id, limit=6)
            reply = generate_reply(text, contact, history=history)
        # حفظ التبادل في ذاكرة المحادثات (whatsapp_chats)
        database.save_chat(wa_id, text, reply)
        if mode == "send" and reply:
            res = send_whatsapp_message(wa_id, reply)
            status = "sent" if res.get("ok") else "failed"
            db.log_wa_message(wa_id, "out", reply, status)
            actions.append({"wa_id": wa_id, "mode": "send", "status": status})
        else:
            db.log_wa_message(wa_id, "draft", reply, "draft")
            actions.append({"wa_id": wa_id, "mode": "draft", "status": "draft"})
    return actions


# --------------------------------------------------------------------------
# 4) تطبيق Flask (الويبهوك) — استيراد كسول حتى لا يلزم Flask لاستخدام الدوال أعلاه
# --------------------------------------------------------------------------
def create_app():
    from flask import Flask, request, jsonify
    flask_app = Flask(__name__)

    @flask_app.get("/health")
    def health():
        return {"status": "ok"}, 200

    @flask_app.get("/webhook")
    def verify():
        # تحقّق Meta من الويبهوك
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == os.environ.get("WA_VERIFY_TOKEN"):
            return challenge or "", 200
        return "forbidden", 403

    @flask_app.post("/webhook")
    def receive():
        payload = request.get_json(silent=True) or {}
        actions = handle_incoming(payload)
        return jsonify({"received": True, "actions": actions}), 200

    return flask_app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    create_app().run(host="0.0.0.0", port=port)
