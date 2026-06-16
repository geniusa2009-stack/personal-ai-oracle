"""
features.py — سجل الـ50 ميزة + موزّع التشغيل (Feature Registry & Dispatcher)
Infrastructure for the 50 Ultimate Agent features.

كل ميزة لها:
  id, name, cat (الفئة), status (الحالة), kind (نوع المنفّذ), instruction/note.

الحالات (status):
  - active       : تشتغل دلوقتي فعلياً.
  - beta         : تشتغل كأفضل-جهد عبر الذكاء الاصطناعي/البحث.
  - integration  : البنية جاهزة، لكنها تحتاج ربطاً خارجياً (API/صلاحيات) لتعمل كلياً.

الأنواع (kind):
  llm | content | search | radar_opp | radar_jobs | radar_courses |
  radar_grants | whatsapp | scheduler | scaffold
"""

import os
import json

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

CATEGORIES = {
    "life":   "🧭 إدارة الحياة والأهداف",
    "social": "📣 الأتمتة والسوشيال ميديا",
    "search": "🔭 البحث واقتناص الفرص",
    "money":  "💰 المال والبيزنس الشخصي",
    "health": "❤️‍🔥 الصحة والطاقة والأداء",
}

STATUS_BADGE = {"active": "🟢 فعّالة", "beta": "🟡 تجريبية", "integration": "🔌 تحتاج ربط"}


# --------------------------------------------------------------------------
# سجل الميزات الـ50
# --------------------------------------------------------------------------
def _f(id, name, cat, status, kind, instruction="", note=""):
    return {"id": id, "name": name, "cat": cat, "status": status,
            "kind": kind, "instruction": instruction, "note": note}


FEATURES = [
    # [1-10] إدارة الحياة والأهداف
    _f(1, "تحليل المشاعر التلقائي", "life", "active", "llm",
       "حلّل مشاعر النص وكشف الحالة المزاجية والأنماط الخفية، ونصيحة عملية."),
    _f(2, "رادار كشف الفرص والمنح", "life", "active", "radar_opp"),
    _f(3, "تتبّع العادات", "life", "beta", "llm",
       "حوّل كلام المستخدم لخطة تتبّع عادات: عادة، مؤشر نجاح يومي، وتذكير بسيط."),
    _f(4, "كاشف التسويف", "life", "beta", "llm",
       "اكتشف علامات التسويف في النص، سببها الحقيقي، وأصغر خطوة لكسر الجمود دلوقتي."),
    _f(5, "مفكرة الأحلام التنبؤية", "life", "beta", "llm",
       "فسّر الحلم/الفكرة واربطه بأهداف المستخدم ومخاوفه، باحترام وبدون خرافة."),
    _f(6, "منبّه الذكاء العاطفي", "life", "beta", "llm",
       "اقترح رد فعل عاطفي ذكي ومتزن للموقف المكتوب، وكلمات مناسبة للتعبير."),
    _f(7, "ميزان الإنتاجية", "life", "beta", "llm",
       "قيّم توازن يوم المستخدم بين الإنجاز/الراحة/التشتت، واقترح تعديلاً واحداً."),
    _f(8, "مدرب اتخاذ القرار", "life", "active", "llm",
       "ساعد في القرار: المزايا/العيوب، السيناريوهات، والتوصية مع سبب واضح."),
    _f(9, "فلتر الأولويات", "life", "active", "llm",
       "رتّب المهام المكتوبة حسب الأهم/العاجل (مصفوفة أيزنهاور) وابدأ بإيه."),
    _f(10, "مستشار القراءة الذكي", "life", "beta", "llm",
       "رشّح كتب/مقالات تناسب اهتمام المستخدم، وليه كل ترشيح، ومن أين يبدأ."),

    # [11-20] الأتمتة والسوشيال ميديا
    _f(11, "الرد الآلي على الواتساب بالعامية", "social", "active", "whatsapp"),
    _f(12, "كاتب كومنتات الجروبات", "social", "beta", "content"),
    _f(13, "صائد تريندات تيك توك وفيسبوك", "social", "beta", "search",
       note="للتغطية الكاملة (داتا تريندات لحظية) يلزم ربط API رسمي للمنصّة."),
    _f(14, "حارس الموافقة البشرية قبل النشر", "social", "active", "scaffold",
       note="مفعّل فعلياً: وضع المسودّة في الواتساب لا يرسل أي رد إلا بعد موافقتك."),
    _f(15, "جدولة المنشورات التلقائية", "social", "integration", "scaffold",
       note="يحتاج ربط حساب النشر (Meta/X API) + مهمة مجدولة. البنية جاهزة."),
    _f(16, "فلتر الرسائل المزعجة", "social", "beta", "llm",
       "صنّف الرسالة: مزعجة/سبام أم مهمة، مع نسبة ثقة وسبب مختصر."),
    _f(17, "ملخص إشعارات اليوم", "social", "integration", "scaffold",
       note="يحتاج صلاحية قراءة الإشعارات من النظام. يمكن لصق الإشعارات يدوياً للتلخيص."),
    _f(18, "ردود الطوارئ الذكية", "social", "beta", "llm",
       "اكتب ردوداً سريعة مهذّبة لموقف طارئ (اعتذار/تأجيل/انشغال) بالعامية."),
    _f(19, "صانع محتوى ميمز رائج", "social", "beta", "content"),
    _f(20, "مرسل تقارير تلغرام التلقائي", "social", "integration", "scaffold",
       note="يحتاج Telegram Bot Token + chat_id. أضفهما في البيئة لتفعيل الإرسال."),

    # [21-30] البحث واقتناص الفرص
    _f(21, "مفتش مواقع التوظيف 24 ساعة", "search", "active", "radar_jobs"),
    _f(22, "رادار المنح العالمية المحدّث", "search", "active", "radar_grants"),
    _f(23, "كاشف الكورسات المجانية", "search", "active", "radar_courses"),
    _f(24, "باحث جوجل الذاتي", "search", "active", "search"),
    _f(25, "ملخّص مقالات الويب الطويلة", "search", "beta", "llm",
       "لخّص النص/المقال المُعطى في نقاط واضحة + خلاصة سطر واحد.",
       note="لجلب المقال من رابط مباشرة يلزم تفعيل جالب صفحات. الآن: الصق النص."),
    _f(26, "صائد الكتب النادرة", "search", "beta", "search"),
    _f(27, "فلتر الأخبار اليومي المخصّص", "search", "beta", "search"),
    _f(28, "كاشف المؤتمرات والفعاليات", "search", "beta", "search"),
    _f(29, "رادار الشركاء والمستثمرين", "search", "beta", "search"),
    _f(30, "محاكي المقابلات الشخصية", "search", "active", "llm",
       "اعمل محاكاة مقابلة: اسأل أسئلة واقعية حسب الوظيفة، وقيّم الإجابة بنصائح."),

    # [31-40] المال والبيزنس
    _f(31, "متتبّع المصاريف من الرسائل", "money", "integration", "scaffold",
       note="يحتاج صلاحية قراءة رسائل البنك/SMS. البنية جاهزة لتحليلها عند توفّرها."),
    _f(32, "كاشف فرص الفريلانس", "money", "beta", "search"),
    _f(33, "مقيّم أفكار المشاريع", "money", "active", "llm",
       "قيّم فكرة المشروع: السوق، التميّز، المخاطر، ونموذج ربح مبدئي، وقرار اذهب/توقف."),
    _f(34, "مخطّط الميزانية المرن", "money", "beta", "llm",
       "اقترح توزيع ميزانية مرن (50/30/20 معدّل) حسب دخل/أهداف المستخدم."),
    _f(35, "منبّه الفواتير والاشتراكات", "money", "integration", "scaffold",
       note="يحتاج إدخال مواعيد الفواتير + مهمة مجدولة للتذكير. البنية جاهزة."),
    _f(36, "صانع خطط العمل التجارية", "money", "active", "llm",
       "اكتب خطة عمل مختصرة: المشكلة، الحل، السوق، الإيرادات، وخطوات أول 90 يوم."),
    _f(37, "محلّل أسعار الكورسات والأدوات", "money", "beta", "search"),
    _f(38, "مستشار الادخار والاستثمار", "money", "beta", "llm",
       "اشرح خيارات ادخار/استثمار عامة ومبسّطة. وضّح إنها معلومات لا نصيحة مالية."),
    _f(39, "كاتب الإيميلات المهنية", "money", "active", "llm",
       "اكتب إيميل مهني واضح ومهذّب حسب الهدف المطلوب (طلب/متابعة/اعتذار)."),
    _f(40, "منظّم العقود والملفات القانونية", "money", "beta", "llm",
       "لخّص بنود العقد وبسّطها ووضّح النقاط المهمة. ذكّر إنها ليست استشارة قانونية."),

    # [41-50] الصحة والطاقة والأداء
    _f(41, "متتبّع جودة النوم", "health", "integration", "scaffold",
       note="يحتاج ربط سوار/تطبيق صحة (Apple Health/Google Fit). يمكن الإدخال اليدوي."),
    _f(42, "منبّه شرب الماء والحركة", "health", "integration", "scaffold",
       note="يحتاج مهمة مجدولة لإرسال تذكيرات دورية. البنية جاهزة."),
    _f(43, "منظّم الوجبات الصحي", "health", "active", "llm",
       "اقترح خطة وجبات صحية بسيطة ليوم، تناسب أهداف/ميزانية المستخدم."),
    _f(44, "محلّل مستويات التوتر", "health", "beta", "llm",
       "قيّم مستوى التوتر من النص، مسبباته، وتمرين تهدئة فوري."),
    _f(45, "موسيقى التركيز المخصّصة", "health", "integration", "scaffold",
       note="يحتاج ربط مشغّل (Spotify/YouTube API). يمكن اقتراح قوائم بالأسماء الآن."),
    _f(46, "مستشار التخلص من تشتّت الشاشات", "health", "beta", "llm",
       "اقترح خطة عملية لتقليل تشتت الشاشات وزيادة التركيز، بخطوات صغيرة."),
    _f(47, "مدرب التنفّس والهدوء", "health", "active", "llm",
       "اشرح تمرين تنفّس مناسب للحالة (4-7-8 أو صندوقي) خطوة بخطوة بالعامية."),
    _f(48, "منبّه موعد النوم الذكي", "health", "integration", "scaffold",
       note="يحتاج مهمة مجدولة + هدف ساعات النوم. البنية جاهزة للتذكير الليلي."),
    _f(49, "كاشف أعراض الإرهاق الرقمي", "health", "beta", "llm",
       "اكتشف علامات الإرهاق الرقمي من وصف المستخدم واقترح استراحة رقمية مناسبة."),
    _f(50, "محفّز الصباح المخصّص بالعامية", "health", "active", "llm",
       "اكتب رسالة تحفيز صباحية قصيرة بالعامية المصرية حسب أهداف اليوم."),
]

FEATURE_BY_ID = {f["id"]: f for f in FEATURES}


# --------------------------------------------------------------------------
# منفّذ عام للذكاء الاصطناعي (بالعامية المصرية)
# --------------------------------------------------------------------------
def llm_feature(name: str, instruction: str, user_input: str) -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return "⚠️ أضف مفتاح OpenRouter في القائمة الجانبية لتشغيل هذه الميزة."
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    system = ("إنت مساعد مصري ذكي بترد بالعامية المصرية الطبيعية، عملي ومباشر "
              "وبتدّي خطوات واضحة. " + instruction)
    user = user_input.strip() or "(المستخدم لم يكتب تفاصيل — اطلب منه التفاصيل الناقصة باختصار.)"
    try:
        r = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps({"model": model, "temperature": 0.7,
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": user}]}),
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(تعذّر التشغيل: {e})"


# --------------------------------------------------------------------------
# الموزّع (Dispatcher)
# --------------------------------------------------------------------------
def run_feature(feature_id: int, user_input: str = "") -> dict:
    f = FEATURE_BY_ID.get(feature_id)
    if not f:
        return {"name": "غير معروف", "status": "error", "result": "ميزة غير موجودة."}

    kind = f["kind"]
    result = ""
    try:
        if kind == "llm":
            result = llm_feature(f["name"], f["instruction"], user_input)

        elif kind == "content":
            import content_factory
            ctype = "كابشن ميمز" if "ميمز" in f["name"] else "كومنت جروب"
            result = content_factory.generate_content(ctype, user_input or f["name"], save=True)

        elif kind == "search":
            from search import web_search
            q = user_input.strip() or f["name"]
            rows = web_search(q, 5)
            result = ("\n".join(f"- {r['title']} — {r['url']}" for r in rows if r.get("url"))
                      or "مفيش نتائج دلوقتي (أو محرك البحث محتاج TAVILY_API_KEY على السحابة).")

        elif kind in ("radar_opp", "radar_jobs", "radar_courses"):
            import db
            cat = {"radar_opp": None, "radar_jobs": "jobs", "radar_courses": "courses"}[kind]
            opps = db.list_opportunities(category=cat, limit=15)
            if opps:
                result = "\n".join(f"- [{o['score']}%] {o['title']} — {o['url']}" for o in opps)
            else:
                result = "لسه مفيش فرص محفوظة. الرادار بيتجمّع تلقائياً في الخلفية."

        elif kind == "radar_grants":
            import database
            sc = database.list_discovered_scholarships(limit=15)
            result = ("\n".join(f"- {s['name']} — {s['url']}" for s in sc)
                      if sc else "لسه مفيش منح مكتشفة. هتتجمّع تلقائياً من الرادار.")

        elif kind == "whatsapp":
            import whatsapp_agent
            sample = whatsapp_agent.generate_reply(
                user_input or "عامل ايه يا نجم؟", {"relationship": "friend", "name": ""})
            result = ("نموذج رد بالعامية (وضع المسودّة لا يرسل إلا بعد موافقتك):\n\n"
                      + (sample or "أضف مفتاح OpenRouter لتوليد الرد."))

        elif kind == "scaffold":
            result = "🔌 هذه الميزة بنيتها جاهزة وتحتاج ربطاً خارجياً.\n\n" + (f["note"] or "")

        else:
            result = "نوع منفّذ غير معروف."
    except Exception as e:
        result = f"(خطأ أثناء التشغيل: {e})"

    # تسجيل التشغيل في قاعدة البيانات
    try:
        import database
        database.log_feature(f["id"], f["name"], f["status"], result[:300])
    except Exception:
        pass

    return {"name": f["name"], "status": f["status"], "result": result}


def features_by_category() -> dict:
    out = {c: [] for c in CATEGORIES}
    for f in FEATURES:
        out[f["cat"]].append(f)
    return out


def counts() -> dict:
    c = {"active": 0, "beta": 0, "integration": 0}
    for f in FEATURES:
        c[f["status"]] = c.get(f["status"], 0) + 1
    c["total"] = len(FEATURES)
    return c


if __name__ == "__main__":
    print("إجمالي:", counts())
    for cat, items in features_by_category().items():
        print(f"\n{CATEGORIES[cat]}")
        for f in items:
            print(f"  #{f['id']:>2} {STATUS_BADGE[f['status']]}  {f['name']}")
