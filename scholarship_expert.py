"""
scholarship_expert.py — خبير المنح الدراسية
Scholarship Expert: a seed knowledge base of real global/MENA scholarships +
a custom filter/search engine + an Egyptian-dialect answer generator.

⚠️ المواعيد النهائية تتغيّر سنوياً — القاعدة هنا تعطي النوافذ التقريبية المعتادة،
والإجابة النهائية تنصح دائماً بمراجعة الموقع الرسمي وتستعين بالبحث الحيّ للمواعيد الحالية.
"""

import os
import re
import json

import requests

from search import web_search

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# --------------------------------------------------------------------------
# قاعدة المعرفة الأولية (مصادر رسمية معروفة — راجع الموقع لكل تحديث)
# --------------------------------------------------------------------------
SCHOLARSHIPS = [
    {
        "name": "Fulbright", "provider": "حكومة الولايات المتحدة",
        "country": "USA", "levels": ["master", "phd", "research"],
        "fields": ["all"], "funding": "full",
        "typical_deadline": "أبريل–مايو (للدورة التالية)",
        "eligibility": "خريجو جامعات بتقدير جيد جداً، إجادة إنجليزي (TOEFL/IELTS).",
        "url": "https://foreign.fulbrightonline.org",
        "tags": ["أمريكا", "ممولة بالكامل", "ماجستير", "دكتوراه"],
    },
    {
        "name": "Chevening", "provider": "حكومة المملكة المتحدة",
        "country": "UK", "levels": ["master"], "fields": ["all"], "funding": "full",
        "typical_deadline": "أغسطس–نوفمبر",
        "eligibility": "سنتان خبرة عمل، قبول في جامعة بريطانية، قيادة مجتمعية.",
        "url": "https://www.chevening.org",
        "tags": ["بريطانيا", "ممولة بالكامل", "ماجستير سنة واحدة"],
    },
    {
        "name": "DAAD", "provider": "الهيئة الألمانية للتبادل الأكاديمي",
        "country": "Germany", "levels": ["master", "phd", "research"],
        "fields": ["all"], "funding": "full",
        "typical_deadline": "تختلف حسب البرنامج (غالباً أكتوبر–ديسمبر)",
        "eligibility": "خريجون، خبرة عمل لبعض البرامج، إجادة لغة (إنجليزي/ألماني).",
        "url": "https://www.daad.de/en",
        "tags": ["ألمانيا", "ممولة", "ماجستير", "دكتوراه", "بحث"],
    },
    {
        "name": "Erasmus Mundus (EMJM)", "provider": "الاتحاد الأوروبي",
        "country": "EU", "levels": ["master"], "fields": ["all"], "funding": "full",
        "typical_deadline": "أكتوبر–يناير",
        "eligibility": "بكالوريوس، دراسة في أكثر من دولة أوروبية ضمن البرنامج.",
        "url": "https://www.eacea.ec.europa.eu/scholarships/emjmd-catalogue_en",
        "tags": ["أوروبا", "ممولة بالكامل", "ماجستير مشترك"],
    },
    {
        "name": "Türkiye Bursları", "provider": "حكومة تركيا",
        "country": "Türkiye", "levels": ["bachelor", "master", "phd"],
        "fields": ["all"], "funding": "full",
        "typical_deadline": "يناير–فبراير",
        "eligibility": "متاحة للبكالوريوس والدراسات العليا، تشمل سكن ومعيشة وطيران.",
        "url": "https://www.turkiyeburslari.gov.tr",
        "tags": ["تركيا", "بكالوريوس", "ممولة بالكامل", "سهلة التقديم"],
    },
    {
        "name": "MEXT", "provider": "حكومة اليابان",
        "country": "Japan", "levels": ["bachelor", "master", "phd", "research"],
        "fields": ["all"], "funding": "full",
        "typical_deadline": "مايو–يونيو (مسار السفارة)",
        "eligibility": "حسب السن والمؤهل، عبر السفارة اليابانية أو الجامعة.",
        "url": "https://www.studyinjapan.go.jp/en",
        "tags": ["اليابان", "ممولة بالكامل", "بكالوريوس", "دراسات عليا"],
    },
    {
        "name": "Australia Awards", "provider": "حكومة أستراليا",
        "country": "Australia", "levels": ["master", "phd"], "fields": ["all"],
        "funding": "full", "typical_deadline": "أبريل–يونيو",
        "eligibility": "لدول محددة، التزام بالعودة بعد التخرج لفترة.",
        "url": "https://www.dfat.gov.au/people-to-people/australia-awards",
        "tags": ["أستراليا", "ممولة بالكامل"],
    },
    {
        "name": "Knight-Hennessy Scholars", "provider": "جامعة ستانفورد",
        "country": "USA", "levels": ["master", "phd"], "fields": ["all"],
        "funding": "full", "typical_deadline": "أكتوبر",
        "eligibility": "تميّز أكاديمي وقيادي عالٍ، أي تخصص دراسات عليا في ستانفورد.",
        "url": "https://knight-hennessy.stanford.edu",
        "tags": ["أمريكا", "ستانفورد", "تنافسية جداً"],
    },
    {
        "name": "Mastercard Foundation Scholars", "provider": "مؤسسة ماستركارد",
        "country": "Multiple", "levels": ["bachelor", "master"], "fields": ["all"],
        "funding": "full", "typical_deadline": "تختلف حسب الجامعة الشريكة",
        "eligibility": "تركيز على طلاب أفريقيا والاحتياج المادي والقيادة.",
        "url": "https://mastercardfdn.org/all/scholars",
        "tags": ["أفريقيا", "ممولة بالكامل", "احتياج مادي"],
    },
    {
        "name": "GREAT Scholarships", "provider": "British Council وجامعات بريطانية",
        "country": "UK", "levels": ["master"], "fields": ["all"], "funding": "partial",
        "typical_deadline": "تختلف حسب الجامعة (غالباً حتى مايو)",
        "eligibility": "منح جزئية (£10k) لدول محددة منها مصر.",
        "url": "https://study-uk.britishcouncil.org/scholarships/great-scholarships",
        "tags": ["بريطانيا", "جزئية", "مصر مؤهلة"],
    },
    {
        "name": "Nile University Scholarships", "provider": "جامعة النيل (مصر)",
        "country": "Egypt", "levels": ["bachelor", "master"], "fields": ["engineering", "business", "it"],
        "funding": "partial", "typical_deadline": "تختلف (قبل بداية الفصل)",
        "eligibility": "منح تفوق جزئية/كاملة لطلاب متميزين داخل مصر.",
        "url": "https://nu.edu.eg",
        "tags": ["مصر", "محلية", "تفوق"],
    },
    {
        "name": "ITIDA / وزارة الاتصالات (مصر)", "provider": "ITIDA",
        "country": "Egypt", "levels": ["training", "master"], "fields": ["it", "ai", "data"],
        "funding": "partial", "typical_deadline": "دورات دورية على مدار السنة",
        "eligibility": "منح تدريب وتأهيل تقني للمصريين في مجالات IT والذكاء الاصطناعي.",
        "url": "https://itida.gov.eg",
        "tags": ["مصر", "تكنولوجيا", "تدريب", "ذكاء اصطناعي"],
    },
]

LEVEL_SYNONYMS = {
    "bachelor": ["bachelor", "بكالوريوس", "ليسانس", "undergraduate"],
    "master": ["master", "ماجستير", "masters", "msc", "ma"],
    "phd": ["phd", "دكتوراه", "doctorate", "doctoral"],
    "research": ["research", "بحث", "باحث", "postdoc"],
    "training": ["training", "تدريب", "كورس", "دبلومة"],
}

COUNTRY_HINTS = {
    "USA": ["amريكا", "أمريكا", "امريكا", "usa", "us", "united states", "الولايات"],
    "UK": ["بريطانيا", "انجلترا", "إنجلترا", "uk", "britain", "england"],
    "Germany": ["ألمانيا", "المانيا", "germany"],
    "EU": ["أوروبا", "اوروبا", "europe", "eu"],
    "Türkiye": ["تركيا", "turkey", "türkiye"],
    "Japan": ["اليابان", "يابان", "japan"],
    "Australia": ["أستراليا", "استراليا", "australia"],
    "Egypt": ["مصر", "egypt", "محلي", "محلية"],
}

SCHOLARSHIP_TRIGGERS = [
    "منحة", "منح", "scholarship", "grant", "fellowship", "تمويل", "ممول",
    "ابتعاث", "بعثة", "fulbright", "chevening", "daad", "erasmus", "mext",
    "ماجستير", "دكتوراه", "بكالوريوس", "study abroad", "دراسة في الخارج",
]


# --------------------------------------------------------------------------
# الكشف والفلترة
# --------------------------------------------------------------------------
def is_scholarship_query(text: str) -> bool:
    t = (text or "").lower()
    return any(trig in t for trig in SCHOLARSHIP_TRIGGERS)


def detect_filters(text: str) -> dict:
    t = (text or "").lower()
    level = next((lv for lv, syns in LEVEL_SYNONYMS.items()
                  if any(s in t for s in syns)), None)
    country = next((c for c, hints in COUNTRY_HINTS.items()
                    if any(h in t for h in hints)), None)
    return {"level": level, "country": country}


def search_scholarships(query: str = "", level: str = None,
                        country: str = None, limit: int = 8) -> list:
    """فلترة وترتيب المنح من قاعدة المعرفة حسب المعايير."""
    q = (query or "").lower()
    q_tokens = [w for w in re.split(r"\W+", q) if len(w) > 2]
    scored = []
    for s in SCHOLARSHIPS:
        if level and level not in s["levels"]:
            continue
        if country and s["country"] != country and s["country"] not in ("Multiple", "EU"):
            continue
        score = 0
        hay = " ".join([s["name"], s["provider"], s["country"],
                        " ".join(s["fields"]), " ".join(s["tags"])]).lower()
        for tok in q_tokens:
            if tok in hay:
                score += 2
        if level and level in s["levels"]:
            score += 3
        if country and s["country"] == country:
            score += 3
        if s["funding"] == "full":
            score += 1
        scored.append((score, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [s for sc, s in scored if (sc > 0 or not q_tokens)]
    return results[:limit]


def format_scholarship(s: dict) -> str:
    fund = "ممولة بالكامل ✅" if s["funding"] == "full" else "تمويل جزئي"
    return (f"**{s['name']}** — {s['provider']} ({s['country']})\n"
            f"- التمويل: {fund}\n"
            f"- المستويات: {', '.join(s['levels'])}\n"
            f"- الموعد التقريبي: {s['typical_deadline']}\n"
            f"- الشروط باختصار: {s['eligibility']}\n"
            f"- الرابط الرسمي: {s['url']}")


# --------------------------------------------------------------------------
# توليد الإجابة (بالعامية المصرية) + بحث حيّ اختياري
# --------------------------------------------------------------------------
def _llm(prompt: str, system: str) -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    if not key:
        return ""
    try:
        r = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps({
                "model": model, "temperature": 0.6,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": prompt}],
            }),
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return ""


def answer_scholarship_query(text: str, use_web: bool = True) -> str:
    """يجمع منح القاعدة + بحث حيّ + يصيغ إجابة عملية بالعامية المصرية."""
    filters = detect_filters(text)
    kb_matches = search_scholarships(text, filters["level"], filters["country"])
    kb_block = "\n\n".join(format_scholarship(s) for s in kb_matches) or "لا يوجد تطابق مباشر في القاعدة."

    web_block = ""
    if use_web:
        q = text.strip()
        live = web_search(f"{q} scholarship 2026 deadline apply", 5)
        if live:
            web_block = "\n".join(
                f"- {r['title']} — {r['url']}" for r in live if r.get("url"))
            # حفظ المنح المكتشفة من البحث الحيّ تلقائياً
            try:
                import database
                database.save_scholarships([{
                    "name": r.get("title", ""), "url": r.get("url", ""),
                    "requirements": r.get("snippet", ""), "source": "scholarship_expert",
                } for r in live if r.get("url")])
            except Exception:
                pass

    system = (
        "إنت خبير منح دراسية بتتكلم بالعامية المصرية البسيطة والذكية. "
        "ردك عملي ومباشر، بتدّي خطوات وروابط، وبتنبّه إن المواعيد بتتغيّر كل سنة "
        "فلازم يراجع الموقع الرسمي. متخترعش مواعيد دقيقة."
    )
    prompt = (
        f"سؤال المستخدم: {text}\n\n"
        f"منح من قاعدة المعرفة:\n{kb_block}\n\n"
        f"نتائج بحث حيّة (للمواعيد الحالية، راجعها):\n{web_block or 'لا يوجد'}\n\n"
        "اكتب رد منظّم بالعامية المصرية: المنح الأنسب ليه، شروطها باختصار، "
        "الخطوة الجاية اللي يعملها، ولينكات يدخل عليها. ونبّهه يراجع المواعيد الرسمية."
    )
    answer = _llm(prompt, system)
    if answer:
        return answer
    # fallback بدون مفتاح AI: نعرض القاعدة منسّقة
    note = "\n\n📌 ملاحظة: المواعيد تقريبية وبتتغيّر سنوياً — راجع الموقع الرسمي لكل منحة."
    return "أقرب منح ليك من قاعدة المعرفة:\n\n" + kb_block + note


if __name__ == "__main__":
    print(answer_scholarship_query("عايز منحة ماجستير ممولة في ألمانيا", use_web=False))
