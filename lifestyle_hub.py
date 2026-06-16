"""
lifestyle_hub.py — أسلوب الحياة الفائق والتحكم التلقائي (الميزات 41-50)
"""

import ai_core

SECTION = {"key": "lifestyle", "label": "✨ أسلوب الحياة الفائق والتحكم التلقائي"}

FEATURES = [
    {"id": 41, "name": "نشرة بودكاست يومية شخصية", "status": "integration", "kind": "scaffold",
     "note": "النص جاهز للتوليد؛ تحويله لصوت يحتاج ربط TTS (ElevenLabs/Google). "
             "أضف المفتاح لتفعيل الصوت."},
    {"id": 42, "name": "منسّق الإطلالات", "status": "active", "kind": "llm", "mode": "friendly",
     "instruction": "خُد قائمة الملابس المتوفرة واقترح أطقم متناسقة تناسب مود وخروج اليوم."},
    {"id": 43, "name": "مؤقّت بومودورو متكيّف", "status": "beta", "kind": "llm", "mode": "coach",
     "instruction": "صمّم خطة بومودورو متكيّفة (مدد تركيز/راحة) حسب حالة التشتت الموصوفة.",
     "note": "المؤقّت التفاعلي اللحظي يحتاج تشغيله في الواجهة."},
    {"id": 44, "name": "رادار أدوات الذكاء الاصطناعي", "status": "beta", "kind": "search",
     "query": "newest AI tools this week {q}"},
    {"id": 45, "name": "دليل فينج شوي المكتب", "status": "active", "kind": "llm", "mode": "coach",
     "instruction": "حلّل وصف مكتب/بيئة المستخدم واقترح ترتيباً يزيد التركيز والراحة."},
    {"id": 46, "name": "منفّذ الالتزام الصارم", "status": "active", "kind": "llm", "mode": "strict",
     "instruction": "لو في تهاون في الأهداف، واجه المستخدم بحزم محترم وحدّد عقوبة/مكافأة "
                    "وخطوة فورية لا تقبل التأجيل."},
    {"id": 47, "name": "رفيق القراءة المشترك", "status": "active", "kind": "llm", "mode": "friendly",
     "instruction": "ضع خطة قراءة سنوية حسب شغف المستخدم، وناقش معه فصول الكتاب بأسئلة عميقة."},
    {"id": 48, "name": "مستكشف الهوايات بعيداً عن الشاشة", "status": "active", "kind": "llm",
     "mode": "friendly",
     "instruction": "اقترح نشاطات وهوايات يدوية/فكرية مبهجة تخرج المستخدم من روتين الشاشات."},
    {"id": 49, "name": "منسّق الديتوكس الرقمي", "status": "beta", "kind": "llm", "mode": "coach",
     "instruction": "صمّم جدول ساعات انفصال رقمي كامل وقواعد لحجب الإشعارات غير الطارئة.",
     "note": "الحجب الفعلي للإشعارات يحتاج صلاحيات نظام/مهمة مجدولة."},
    {"id": 50, "name": "موصّل أحلام الطفولة", "status": "active", "kind": "dream", "mode": "friendly",
     "instruction": "اربط يوميات المستخدم الحالية بأحلام طفولته وأهدافه الأساسية، "
                    "واكتب رسالة فخر دافئة بالعامية المصرية توضّح قد إيه قرّب من حلمه."},
]

BY_ID = {f["id"]: f for f in FEATURES}


def dream_connector(user_input: str) -> str:
    """يقرأ آخر اليوميات ويربطها بحلم/هدف المستخدم برسالة فخر بالعامية."""
    context = ""
    try:
        import db
        conn = db.get_conn()
        rows = conn.execute("SELECT text FROM entries ORDER BY id DESC LIMIT 6").fetchall()
        conn.close()
        context = "\n".join(f"- {r['text'][:200]}" for r in rows if r["text"])
    except Exception:
        context = ""
    payload = (f"حلم/هدف المستخدم: {user_input or '(غير محدد — استنتجه من اليوميات)'}\n\n"
               f"مقتطفات من يومياته الأخيرة:\n{context or '(لا توجد يوميات بعد)'}")
    return ai_core.llm(BY_ID[50]["instruction"], payload, "friendly")


def run(feature_id: int, user_input: str = "") -> str:
    f = BY_ID.get(feature_id)
    if not f:
        return "ميزة غير موجودة."
    if f["kind"] == "dream":
        return dream_connector(user_input)
    if f["kind"] == "scaffold":
        return "🔌 " + f.get("note", "تحتاج ربطاً خارجياً.")
    if f["kind"] == "search":
        from search import web_search
        q = f.get("query", "{q}").format(q=user_input.strip())
        rows = web_search(q, 5)
        return ("\n".join(f"- {r['title']} — {r['url']}" for r in rows if r.get("url"))
                or "مفيش نتائج دلوقتي (ممكن يحتاج TAVILY_API_KEY على السحابة).")
    return ai_core.llm(f["instruction"], user_input, f.get("mode", "friendly"))
