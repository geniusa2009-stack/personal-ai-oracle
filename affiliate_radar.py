"""
affiliate_radar.py — رادار التسويق بالعمولة عالي القيمة (الميزات 51-75)
ملاحظة امتثال: التعليق الآلي بروابط على بوستات الناس = سبام (موقوف). وإخفاء كون الرابط
عمولة = تضليل وممنوع قانونياً؛ البديل: روابط مع إفصاح واضح. التحليلات والمراجعات تعمل فعلياً.
"""

import ai_core
import database

SECTION = {"key": "affiliate", "label": "🔗 رادار التسويق بالعمولة عالي القيمة"}
DISCLOSE = "ملاحظة مدمجة: المراجعات تتضمّن إفصاحاً واضحاً بأن الرابط رابط عمولة (مطلوب قانونياً)."


def _f(i, name, status, kind, instruction="", note="", mode="friendly"):
    return {"id": i, "name": name, "status": status, "kind": kind,
            "instruction": instruction, "note": note, "mode": mode}


FEATURES = [
    _f(51, "باحث Amazon Egypt", "beta", "search"),
    _f(52, "باحث ClickBank", "beta", "search"),
    _f(53, "باحث CJ Affiliate", "beta", "search"),
    _f(54, "باحث Impact", "beta", "search"),
    _f(55, "صائد العمولات المرتفعة (High-Ticket)", "beta", "search"),
    _f(56, "كاتب مراجعات فيروسية (بإفصاح)", "active", "llm",
       "اكتب مراجعة بالعامية المصرية جذابة وصادقة، وادمج رابط العمولة مع إفصاح واضح إنه رابط عمولة."),
    _f(57, "كاتب منشور مقارنة منتجات", "active", "llm",
       "اكتب منشور مقارنة بين منتجين بصدق مع رابط العمولة وإفصاح."),
    _f(58, "كاتب قصة تجربة المنتج", "active", "llm",
       "اكتب قصة تجربة واقعية ممتعة للمنتج تنتهي برابط عمولة مُفصح عنه."),
    _f(59, "كاتب زاوية المنفعة", "active", "llm",
       "ركّز على المشكلة التي يحلها المنتج للقارئ، مع رابط مُفصح."),
    _f(60, "محسّن عنوان المراجعة", "active", "llm", "اكتب 5 عناوين جذابة لمراجعة المنتج."),
    _f(61, "تعليق آلي على فيسبوك", "gated", "gated",
       note="وضع روابط آلياً على بوستات الناس = سبام يضر سمعتك وقد يحظرك. البديل: شارك مراجعتك على صفحتك."),
    _f(62, "تعليق آلي على تويتر/X", "gated", "gated",
       note="نفس السبب: التعليق الآلي بالروابط سبام. انشر محتوى قيمة على حسابك بدلاً منه."),
    _f(63, "مراقب منشورات التوصيات", "beta", "search",
       note="رصد المنشورات الباحثة عن توصية للاطلاع فقط؛ الرد يدوي ومحترم بدون سبام."),
    _f(64, "كاشف مجموعات النيتش", "beta", "search"),
    _f(65, "كاتب رد توصية محترم", "active", "llm",
       "اكتب رداً مفيداً حقيقياً على شخص يطلب توصية، مع ذكر إنك تكسب عمولة لو اشترى من رابطك."),
    _f(66, "رابط مختصر مع إفصاح", "active", "llm",
       "صُغ طريقة عرض رابط العمولة باحترافية مع جملة إفصاح واضحة وجذابة."),
    _f(67, "إخفاء كون الرابط عمولة", "gated", "gated",
       note="إخفاء طبيعة رابط العمولة تضليل وممنوع. استخدم الميزة #66: رابط واضح مع إفصاح."),
    _f(68, "تمويه الروابط الربحية", "gated", "gated",
       note="تمويه الروابط لتبدو غير عمولة = خداع. البديل: شفافية + قيمة حقيقية."),
    _f(69, "تدوير روابط مخفية", "gated", "gated", note="ممارسات إخفاء ممنوعة. التزم بالإفصاح."),
    _f(70, "حاقن روابط تلقائي", "gated", "gated", note="حقن الروابط آلياً في محتوى الآخرين سبام."),
    _f(71, "حلقة تحليلات التحويل", "active", "tool",
       "يلخّص أداء روابط العمولة (نقرات/تحويلات/أرباح) ويبرز الأفضل."),
    _f(72, "مكثّف المحتوى الرابح", "active", "llm",
       "بناءً على المنتج الأعلى تحويلاً، اقترح أفكار محتوى إضافية تكثّف الكسب منه."),
    _f(73, "موقف الروابط الضعيفة", "active", "llm",
       "اقترح معايير لإيقاف الترويج لرابط ضعيف الأداء وتحويل الجهد لغيره."),
    _f(74, "محلّل أفضل وقت نشر", "beta", "llm", "اقترح أفضل أوقات نشر مراجعات الأفيليت لجمهورك."),
    _f(75, "مخطّط حملة أفيليت", "active", "llm", "صمّم خطة حملة أفيليت أسبوعية بمحتوى وقنوات."),
]

BY_ID = {f["id"]: f for f in FEATURES}


def conversion_summary() -> str:
    logs = database.list_affiliate_logs(200)
    if not logs:
        return "لا توجد بيانات أفيليت بعد. سجّل روابطك ونقراتها لتظهر التحليلات."
    clicks = sum(l["clicks"] for l in logs)
    convs = sum(l["conversions"] for l in logs)
    rev = sum(l["revenue"] for l in logs)
    rate = round(convs / clicks * 100, 1) if clicks else 0
    best = max(logs, key=lambda l: l["revenue"], default=None)
    return (f"📊 إجمالي النقرات: {clicks} | التحويلات: {convs} | معدل التحويل: {rate}%\n"
            f"الأرباح: {rev:.2f}\n"
            + (f"الأعلى ربحاً: {best['product']} ({best['revenue']:.2f})" if best else ""))


def run(feature_id: int, user_input: str = "") -> str:
    f = BY_ID.get(feature_id)
    if not f:
        return "ميزة غير موجودة."
    if f["kind"] == "gated":
        return "⛔ موقوف لأسباب امتثال.\n" + f.get("note", "")
    if f["kind"] == "tool" and feature_id == 71:
        return conversion_summary()
    if f["kind"] == "search":
        from search import web_search
        q = user_input.strip() or f["name"]
        rows = web_search(f"{q} affiliate program high commission", 5)
        return ("\n".join(f"- {r['title']} — {r['url']}" for r in rows if r.get("url"))
                or "مفيش نتائج دلوقتي (ممكن يحتاج TAVILY_API_KEY على السحابة).")
    out = ai_core.llm(f["instruction"], user_input, f.get("mode", "friendly"))
    return out + ("\n\n— " + DISCLOSE if f["id"] in (56, 57, 58, 59, 65, 66) else "")
