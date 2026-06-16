"""
super_learning.py — التعلّم الخارق والذاكرة الفوتوغرافية (الميزات 11-20)
"""

import ai_core

SECTION = {"key": "learning", "label": "🧠 التعلّم الخارق والذاكرة الفوتوغرافية"}

FEATURES = [
    {"id": 11, "name": "ملخّص الفيديوهات", "status": "beta", "kind": "llm", "mode": "coach",
     "instruction": "لخّص محتوى الفيديو (الصق نصّه/الترانسكريبت) في النقاط الذهبية + خلاصة دقيقة.",
     "note": "لجلب نص يوتيوب آلياً يلزم ربط YouTube Transcript API. الآن: الصق النص."},
    {"id": 12, "name": "مولّد الخرائط الذهنية", "status": "active", "kind": "llm", "mode": "coach",
     "instruction": "حوّل النص الطويل لخريطة ذهنية شجرية نصية مبسّطة (فروع وأفرع بمسافات بادئة)."},
    {"id": 13, "name": "محاكي تقنية فاينمان", "status": "active", "kind": "llm", "mode": "coach",
     "instruction": "اطلب من المستخدم يشرح الفكرة ببساطة، وصحّح الأجزاء غير المفهومة، "
                    "وبسّطها كأنها لطفل، ثم اطرح سؤالاً يختبر فهمه."},
    {"id": 14, "name": "صائد كنوز البودكاست", "status": "beta", "kind": "search",
     "query": "best podcast episode about {q}",
     "note": "يبحث عن حلقات بودكاست مناسبة لمشكلتك."},
    {"id": 15, "name": "مترجم المصطلحات للعامية", "status": "active", "kind": "llm", "mode": "friendly",
     "instruction": "ترجم المصطلح الإنجليزي المعقّد لعامية مصرية مبسّطة مع مثال من الواقع."},
    {"id": 16, "name": "كاشف الإشاعات والمغالطات", "status": "beta", "kind": "llm", "mode": "professional",
     "instruction": "حلّل الادعاء/الخبر منطقياً، بيّن المغالطات المحتملة وما يحتاج تحقّقاً، "
                    "بدون ادعاء يقين مطلق.",
     "note": "ليست قاعدة حقائق لحظية؛ تحليل منطقي + توجيه للتحقق."},
    {"id": 17, "name": "مجدول التكرار المتباعد", "status": "beta", "kind": "llm", "mode": "coach",
     "instruction": "حوّل المعلومة لبطاقات مراجعة بجدول تكرار متباعد (1، 3، 7، 16، 35 يوم)."},
    {"id": 18, "name": "مدرّب البرومبتات المتقدمة", "status": "active", "kind": "llm", "mode": "coach",
     "instruction": "علّم المستخدم يصيغ سؤالاً عبقرياً للنماذج اللغوية: حسّن برومبته وفسّر ليه."},
    {"id": 19, "name": "ملخّص المساقات (MOOCs)", "status": "beta", "kind": "llm", "mode": "coach",
     "instruction": "لخّص محتوى مساق (الصق وصفه/منهجه) كنقاط تعلّم عملية ومسار مذاكرة.",
     "note": "للسحب الآلي من Coursera/edX يلزم ربط؛ الآن الصق الوصف."},
    {"id": 20, "name": "حارس الانتحال الأكاديمي", "status": "beta", "kind": "llm", "mode": "professional",
     "instruction": "أعد صياغة الفقرة بأسلوب أصيل يتجنّب الاقتباس الحرفي ويحافظ على المعنى.",
     "note": "ليس كاشف انتحال بقاعدة بيانات؛ أداة إعادة صياغة."},
]

BY_ID = {f["id"]: f for f in FEATURES}


def run(feature_id: int, user_input: str = "") -> str:
    f = BY_ID.get(feature_id)
    if not f:
        return "ميزة غير موجودة."
    if f["kind"] == "search":
        from search import web_search
        q = f.get("query", "{q}").format(q=user_input.strip() or f["name"])
        rows = web_search(q, 5)
        return ("\n".join(f"- {r['title']} — {r['url']}" for r in rows if r.get("url"))
                or "مفيش نتائج دلوقتي (محرك البحث ممكن يحتاج TAVILY_API_KEY على السحابة).")
    return ai_core.llm(f["instruction"], user_input, f.get("mode", "coach"))
