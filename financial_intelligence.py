"""
financial_intelligence.py — رادار الذكاء المالي وتنمية الثروة (الميزات 21-30)
يجمع بين دوال ذكاء اصطناعي وأدوات حسابية حقيقية وقاعدة بيانات الفواتير/المصاريف.
"""

import re

import ai_core
import database

SECTION = {"key": "money", "label": "💰 رادار الذكاء المالي وتنمية الثروة"}

FEATURES = [
    {"id": 21, "name": "مانع الشراء الاندفاعي", "status": "active", "kind": "llm", "mode": "coach",
     "instruction": "قبل الشراء، اسأل المستخدم أسئلة عقلانية عن مدى حاجته الفعلية للمنتج "
                    "وبدائل أرخص، وساعده ياخد قرار واعٍ."},
    {"id": 22, "name": "مخطّط الادخار المرن", "status": "active", "kind": "llm", "mode": "professional",
     "instruction": "حلّل الدخل والمصاريف وضع خطة ادخار مرنة (تشمل بند «فلوس الدلع») "
                    "بنسب واقعية وخطوات شهرية."},
    {"id": 23, "name": "مراقب الذهب والعملات", "status": "integration", "kind": "scaffold",
     "note": "يحتاج ربط مصدر أسعار لحظي (API ذهب/صرف). البنية جاهزة لاستقبال البيانات وتحليلها."},
    {"id": 24, "name": "محلّل العروض الوهمية", "status": "active", "kind": "tool",
     "instruction": "احسب الخصم الحقيقي قبل/بعد التخفيض."},
    {"id": 25, "name": "مهندس السفر الاقتصادي", "status": "beta", "kind": "search",
     "query": "cheapest flights and budget travel {q}"},
    {"id": 26, "name": "حاسبة الرسوم المخفية", "status": "active", "kind": "tool",
     "instruction": "احسب الإجمالي بعد الضرائب والعمولات المخفية."},
    {"id": 27, "name": "محاكي المشاريع المصغّرة", "status": "active", "kind": "llm", "mode": "coach",
     "instruction": "أدِر مع المستخدم بيزنس وهمي خطوة بخطوة: احسب الإيرادات والتكاليف "
                    "والأرباح/الخسائر وعلّمه القرارات."},
    {"id": 28, "name": "حاضنة الدخل الجانبي", "status": "active", "kind": "llm", "mode": "coach",
     "instruction": "اقترح مهارة رقمية تتعلّم في أسبوع وتبدأ تبيعها كخدمة، مع خطة بدء عملية."},
    {"id": 29, "name": "منظّم الفواتير والاشتراكات", "status": "active", "kind": "tool",
     "instruction": "سجّل الفواتير واحسب المتوسط الشهري."},
    {"id": 30, "name": "رادار التمويل والحاضنات", "status": "beta", "kind": "search",
     "query": "حاضنات أعمال ومنح تمويل مشاريع الشباب في مصر {q}"},
]

BY_ID = {f["id"]: f for f in FEATURES}


def _numbers(text):
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]


def hidden_fees(text: str) -> str:
    """يحسب الإجمالي بعد النسب المخفية. مثال: '1000 + 14% + 2.5%'."""
    base = _numbers(text)
    if not base:
        return "اكتب المبلغ الأساسي والنِّسب، مثال: «1000 + 14% + 2.5%»."
    amount = base[0]
    percents = [float(p) for p in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]
    if not percents:
        return f"المبلغ {amount:.2f} بدون رسوم إضافية مذكورة. أضف النِّسب مثل 14%."
    total = amount
    lines = [f"المبلغ الأساسي: {amount:.2f}"]
    for p in percents:
        fee = amount * p / 100
        total += fee
        lines.append(f"+ رسم {p}%: {fee:.2f}")
    lines.append(f"= الإجمالي الفعلي: {total:.2f}")
    lines.append(f"(الزيادة الكلية: {total - amount:.2f})")
    return "\n".join(lines)


def fake_offer(text: str) -> str:
    """يحسب الخصم الحقيقي من سعرين: قبل وبعد."""
    nums = _numbers(text)
    if len(nums) < 2:
        return "اكتب السعر قبل وبعد الخصم، مثال: «قبل 1000 بعد 850»."
    before, after = max(nums[:2]), min(nums[:2])
    if before <= 0:
        return "السعر غير صالح."
    disc = (before - after) / before * 100
    verdict = ("خصم محترم ✅" if disc >= 20 else
               "خصم بسيط 🤏" if disc >= 5 else "شبه وهمي ⚠️")
    return (f"قبل: {before:.2f} | بعد: {after:.2f}\n"
            f"الخصم الحقيقي: {disc:.1f}% — {verdict}\n"
            f"وفّرت: {before - after:.2f}")


def add_bill_from_text(text: str) -> str:
    """يسجّل فاتورة. صيغة: 'اسم, مبلغ, دورة(شهري/سنوي), الموعد القادم'."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 2:
        return "اكتب: «اسم الفاتورة, المبلغ, الدورة, الموعد القادم»."
    name = parts[0]
    amount = (_numbers(parts[1]) or [0])[0]
    cycle = parts[2] if len(parts) > 2 else "شهري"
    next_due = parts[3] if len(parts) > 3 else ""
    database.add_bill(name, amount, cycle, next_due)
    bills = database.list_bills()
    monthly = sum((b["amount"] or 0) / (12 if "سنوي" in (b["cycle"] or "") else 1)
                  for b in bills)
    lines = "\n".join(f"- {b['name']}: {b['amount']:.0f} ({b['cycle']})"
                      + (f" 📅 {b['next_due']}" if b['next_due'] else "") for b in bills)
    return f"✅ اتسجّلت. متوسط استهلاكك الشهري التقريبي: {monthly:.0f} جنيه\n\n{lines}"


def run(feature_id: int, user_input: str = "") -> str:
    f = BY_ID.get(feature_id)
    if not f:
        return "ميزة غير موجودة."
    if f["kind"] == "tool":
        if feature_id == 24:
            return fake_offer(user_input)
        if feature_id == 26:
            return hidden_fees(user_input)
        if feature_id == 29:
            return add_bill_from_text(user_input)
    if f["kind"] == "scaffold":
        return "🔌 " + f.get("note", "تحتاج ربطاً خارجياً.")
    if f["kind"] == "search":
        from search import web_search
        q = f.get("query", "{q}").format(q=user_input.strip())
        rows = web_search(q, 5)
        return ("\n".join(f"- {r['title']} — {r['url']}" for r in rows if r.get("url"))
                or "مفيش نتائج دلوقتي (ممكن يحتاج TAVILY_API_KEY على السحابة).")
    return ai_core.llm(f["instruction"], user_input, f.get("mode", "professional"))
