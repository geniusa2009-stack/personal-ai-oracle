"""
seo_content_factory.py — شبكة المدونات والمحتوى الربحي والـ SEO (الميزات 76-100)
يعيد استخدام income_hunter (مولّد مقالات SEO + نشر WordPress الفعلي).
"""

import re
import ai_core
import database
import income_hunter

SECTION = {"key": "seo", "label": "📝 شبكة المحتوى الربحي والـ SEO"}


def _f(i, name, status, kind, instruction="", note="", mode="professional"):
    return {"id": i, "name": name, "status": status, "kind": kind,
            "instruction": instruction, "note": note, "mode": mode}


FEATURES = [
    _f(76, "باحث الكلمات عالية الـ CPM", "beta", "search"),
    _f(77, "مولّد أفكار الكلمات المفتاحية", "active", "llm",
       "اقترح 15 كلمة مفتاحية مربحة (long-tail) في المجال مع نية البحث لكل واحدة."),
    _f(78, "محلّل نية البحث", "active", "llm", "صنّف الكلمة المفتاحية حسب نية البحث واقترح نوع المحتوى."),
    _f(79, "مقدّر صعوبة الكلمة", "beta", "llm", "قدّر صعوبة المنافسة على الكلمة واقترح بديلاً أسهل."),
    _f(80, "مخطّط عناقيد المحتوى", "active", "llm", "صمّم Content Cluster (مقال محوري + فرعية) للموضوع."),
    _f(81, "كاتب مقالات SEO", "active", "tool", "يكتب مقالاً كاملاً محسّناً (عنوان/ميتا/عناوين)."),
    _f(82, "كاتب المقدمات الجاذبة", "active", "llm", "اكتب مقدمة مقال تشدّ القارئ وتظهر الكلمة المفتاحية."),
    _f(83, "كاتب الميتا والعناوين", "active", "llm", "اكتب title + meta description مثاليين للكلمة."),
    _f(84, "كاتب الأسئلة الشائعة (FAQ Schema)", "active", "llm", "اكتب 5 أسئلة شائعة بإجابات للـ schema."),
    _f(85, "محسّن قابلية القراءة", "active", "llm", "حسّن فقرة لتكون أوضح وأسهل قراءة مع حفظ الكلمات المفتاحية."),
    _f(86, "ناشر ووردبريس", "active", "tool", "ينشر المقال فعلياً على WordPress عبر REST API."),
    _f(87, "كاتب وصف النشر الاجتماعي", "active", "llm", "اكتب وصفاً للمشاركة على السوشيال عند نشر المقال."),
    _f(88, "مجدول النشر في الذروة", "integration", "scaffold",
       note="الجدولة الآلية تحتاج مهمة مجدولة + إعداد أوقات الذروة. البنية جاهزة."),
    _f(89, "ناشر Blogger", "integration", "scaffold",
       note="يحتاج OAuth مع Google Blogger API. البنية جاهزة لاستقبال البيانات."),
    _f(90, "محوّل المقال لتنسيق ووردبريس", "active", "llm", "حوّل المقال لتنسيق HTML نظيف لووردبريس."),
    _f(91, "مستشار أماكن إعلانات AdSense", "active", "llm",
       "اقترح أفضل أماكن وضع إعلانات AdSense داخل المقال لزيادة الربح دون إزعاج القارئ."),
    _f(92, "محسّن كثافة الإعلانات", "active", "llm", "اقترح توازن عدد الإعلانات مقابل تجربة المستخدم."),
    _f(93, "محلّل CTR الإعلاني", "beta", "llm", "اقترح تحسينات لرفع نسبة الضغط على الإعلانات بشكل مشروع."),
    _f(94, "مخطّط محتوى موسمي", "active", "llm", "اقترح مواضيع موسمية عالية الزيارات في المجال."),
    _f(95, "محسّن سرعة/تجربة الصفحة", "beta", "llm", "نصائح عملية لتحسين سرعة الصفحة و Core Web Vitals."),
    _f(96, "الربط الداخلي الآلي", "active", "tool",
       "يقترح روابط داخلية بين مقالاتك (اكتب عناوين المقالات سطراً لكل واحد)."),
    _f(97, "كاتب نصوص الروابط (Anchor)", "active", "llm", "اقترح نص رابط (anchor) طبيعياً لكل ربط داخلي."),
    _f(98, "بانٍ الـ Topic Authority", "active", "llm", "اقترح خطة لبناء سلطة الموضوع عبر ربط مقالات مترابطة."),
    _f(99, "محسّن وقت بقاء الزائر", "active", "llm", "اقترح عناصر ترفع زمن بقاء الزائر (روابط/أقسام/CTA)."),
    _f(100, "مدقّق روابط مكسورة", "beta", "llm", "نصائح لاكتشاف ومعالجة الروابط الداخلية المكسورة."),
]

BY_ID = {f["id"]: f for f in FEATURES}


def internal_linking(text: str) -> str:
    titles = [t.strip() for t in text.splitlines() if t.strip()]
    if len(titles) < 2:
        return "اكتب عناوين مقالاتك (عنوان في كل سطر) لاقتراح الروابط الداخلية بينها."
    def toks(s):
        return set(w for w in re.split(r"\W+", s.lower()) if len(w) > 2)
    out = []
    for i, t in enumerate(titles):
        scores = sorted(((len(toks(t) & toks(o)), o) for j, o in enumerate(titles) if j != i),
                        reverse=True)
        links = [o for s, o in scores if s > 0][:2] or [scores[0][1]] if scores else []
        out.append(f"• «{t}» → " + (" ، ".join(f"«{l}»" for l in links) or "(لا يوجد تشابه)"))
    return "اقتراحات الربط الداخلي:\n" + "\n".join(out)


def run(feature_id: int, user_input: str = "") -> str:
    f = BY_ID.get(feature_id)
    if not f:
        return "ميزة غير موجودة."
    if f["kind"] == "scaffold":
        return "🔌 " + f.get("note", "تحتاج ربطاً خارجياً.")
    if f["kind"] == "tool":
        if feature_id == 81:
            art = income_hunter.generate_seo_article(user_input or "منح ممولة")
            try:
                database.add_seo_metric(user_input or "منح ممولة", 0, "", "", "drafted")
            except Exception:
                pass
            return f"TITLE: {art['title']}\nMETA: {art['meta']}\n\n{art['content']}"
        if feature_id == 86:
            parts = user_input.split("|", 1)
            title = parts[0].strip() or "مقال جديد"
            body = parts[1].strip() if len(parts) > 1 else ""
            res = income_hunter.publish_to_wordpress(title, body or title)
            return (f"✅ اتنشر: {res.get('link')}" if res.get("ok")
                    else "🔌 " + (res.get("note") or f"تعذّر: {res.get('error')}"))
        if feature_id == 96:
            return internal_linking(user_input)
    if f["kind"] == "search":
        from search import web_search
        q = user_input.strip() or "high CPM keywords"
        rows = web_search(f"{q} high cpm keywords google ads", 5)
        return ("\n".join(f"- {r['title']} — {r['url']}" for r in rows if r.get("url"))
                or "مفيش نتائج دلوقتي (ممكن يحتاج TAVILY_API_KEY على السحابة).")
    return ai_core.llm(f["instruction"], user_input, f.get("mode", "professional"))
