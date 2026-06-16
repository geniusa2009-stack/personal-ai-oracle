"""
social_diplomacy.py — رادار العلاقات والدبلوماسية الاجتماعية (الميزات 1-10)
كل ميزة دالة بنظام توجيه (System Prompt) مخصص. الميزات النصية تشتغل عبر ai_core،
وميزة حافظ الوعود تتخزّن في قاعدة البيانات.
"""

import ai_core
import database

SECTION = {"key": "social", "label": "🤝 رادار العلاقات والدبلوماسية الاجتماعية"}

FEATURES = [
    {"id": 1, "name": "كاشف النوايا والمجاملة المبطّنة", "status": "active", "kind": "llm",
     "mode": "friendly",
     "instruction": "حلّل سياق الرسالة المرسلة واكشف النية المبطّنة أو المصلحة الخفية، "
                    "ونبّه المستخدم بلطف لو في استغلال أو مجاملة زائفة، مع سبب واضح."},
    {"id": 2, "name": "محرّك الصلح والعتاب", "status": "active", "kind": "llm",
     "mode": "friendly",
     "instruction": "اكتب رسالة عتاب/صلح رقيقة وذكية بالعامية المصرية تذوّب الخلاف "
                    "وتحفظ ماء الوجه للطرفين."},
    {"id": 3, "name": "فلتر الفضوليين", "status": "active", "kind": "llm",
     "mode": "friendly",
     "instruction": "صُغ رداً دبلوماسياً مهذّباً يتهرّب من سؤال شخصي/فضولي في جروب "
                    "بدون إحراج وبخفة دم."},
    {"id": 4, "name": "مستشار الكاريزما والحضور", "status": "active", "kind": "llm",
     "mode": "friendly",
     "instruction": "اقترح كلمات مفتاحية وأسلوب رد يدّي كلام المستخدم هيبة وحضوراً "
                    "في نقاش، مع أمثلة جاهزة."},
    {"id": 5, "name": "محسّن شبكة العلاقات", "status": "beta", "kind": "llm",
     "mode": "coach",
     "instruction": "بناءً على معارف المستخدم، اقترح مين يتواصل معاه دلوقتي ولماذا، "
                    "ورسالة افتتاحية قصيرة لكل واحد لتقوية الروابط."},
    {"id": 6, "name": "مصحّح زلّات الغضب", "status": "active", "kind": "llm",
     "mode": "friendly",
     "instruction": "خُد رسالة مكتوبة في حالة غضب وأعد صياغتها بصيغة هادئة وذكية "
                    "تحفظ العلاقة وتوصل المعنى بدون انفعال."},
    {"id": 7, "name": "مستشار الواجبات الاجتماعية", "status": "active", "kind": "llm",
     "mode": "professional",
     "instruction": "صُغ برقية/رسالة مناسبة للثقافة المصرية (عزاء، تهنئة، واجب) "
                    "بكلمات لائقة ومختصرة."},
    {"id": 8, "name": "درع الابتزاز العاطفي", "status": "active", "kind": "llm",
     "mode": "coach",
     "instruction": "اكشف الضغط النفسي أو تحميل الذنب في المحادثة، واشرحه للمستخدم، "
                    "وصُغ رداً حازماً محترماً يحجّم الابتزاز."},
    {"id": 9, "name": "باني الكاريزما الرقمية", "status": "beta", "kind": "llm",
     "mode": "friendly",
     "instruction": "اقترح تعليقات ذكية وراقية يعلّقها المستخدم على بوست مؤثّر "
                    "تلفت الأنظار لذكائه بدون افتعال."},
    {"id": 10, "name": "حافظ الوعود", "status": "active", "kind": "tool",
     "mode": "friendly",
     "instruction": "احفظ الوعود المقطوعة وذكّر بها."},
]

BY_ID = {f["id"]: f for f in FEATURES}


def save_promise(text: str) -> str:
    """يخزّن وعداً في جدول promises. صيغة مرنة: 'لفلان: الوعد @ الموعد'."""
    person, promise, due = "", text.strip(), ""
    if ":" in text:
        person, promise = [p.strip() for p in text.split(":", 1)]
    if "@" in promise:
        promise, due = [p.strip() for p in promise.split("@", 1)]
    if not promise:
        return "اكتب الوعد بصيغة: «اسم الشخص: الوعد @ الموعد»."
    database.add_promise(person or "—", promise, due)
    items = database.list_promises(limit=10)
    lines = "\n".join(f"- {p['person']}: {p['promise']}"
                      + (f" (📅 {p['due']})" if p['due'] else "")
                      + f" [{p['status']}]" for p in items)
    return "✅ اتسجّل الوعد. وعودك الأخيرة:\n" + lines


def run(feature_id: int, user_input: str = "") -> str:
    f = BY_ID.get(feature_id)
    if not f:
        return "ميزة غير موجودة."
    if f["kind"] == "tool" and feature_id == 10:
        return save_promise(user_input)
    return ai_core.llm(f["instruction"], user_input, f.get("mode", "friendly"))
