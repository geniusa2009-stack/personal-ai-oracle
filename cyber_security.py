"""
cyber_security.py — الأمن السيبراني وحماية الخصوصية (الميزات 31-40)
يجمع أدوات حقيقية (مولّد كلمات سر، فاحص روابط، خزنة مشفّرة) + إرشادات ذكية +
هياكل جاهزة للميزات التي تحتاج تكاملاً خارجياً.
"""

import re
import secrets
import string

import ai_core
import database

SECTION = {"key": "cyber", "label": "🛡️ الأمن السيبراني وحماية الخصوصية"}

SUSPICIOUS_TLDS = {".zip", ".mov", ".xyz", ".top", ".tk", ".gq", ".ml", ".cf", ".click", ".loan"}
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "cutt.ly", "is.gd", "rb.gy"}

FEATURES = [
    {"id": 31, "name": "حارس الكاميرا والمايك", "status": "integration", "kind": "scaffold",
     "note": "يحتاج صلاحية مراقبة الوصول للعتاد على مستوى النظام. البنية جاهزة للتنبيه."},
    {"id": 32, "name": "مولّد كلمات السر الخارقة", "status": "active", "kind": "tool",
     "instruction": "يولّد كلمة سر قوية ويخزّنها مشفّرة."},
    {"id": 33, "name": "فاحص روابط التصيّد", "status": "active", "kind": "tool",
     "instruction": "يفحص الرابط لكشف علامات التصيّد."},
    {"id": 34, "name": "ماسح البصمة الرقمية", "status": "beta", "kind": "llm", "mode": "professional",
     "instruction": "ساعد المستخدم يلاقي حساباته القديمة المنسية ويغلقها: قائمة أماكن "
                    "يدوّر فيها وخطوات إغلاق كل نوع حساب."},
    {"id": 35, "name": "بروتوكولات التصفّح الخفي", "status": "beta", "kind": "llm", "mode": "professional",
     "instruction": "اشرح خطوات عملية لتقليل تتبّع شركات الإعلانات أثناء التصفّح "
                    "(إعدادات، إضافات، عادات)."},
    {"id": 36, "name": "الخزنة المشفّرة المحلية", "status": "active", "kind": "tool",
     "instruction": "يخزّن سرّاً مشفّراً محلياً."},
    {"id": 37, "name": "منبّه تسريب البيانات", "status": "integration", "kind": "scaffold",
     "note": "يحتاج ربط خدمة فحص التسريبات (مثل HaveIBeenPwned API). البنية جاهزة للتنبيه."},
    {"id": 38, "name": "فاحص تطبيقات التجسّس", "status": "integration", "kind": "scaffold",
     "note": "يحتاج صلاحية فحص التطبيقات المثبّتة على الجهاز. البنية جاهزة لاستقبال القائمة."},
    {"id": 39, "name": "درع الواي فاي العام", "status": "active", "kind": "llm", "mode": "professional",
     "instruction": "اشرح مخاطر شبكات الواي فاي العامة وخطوات الحماية العملية خطوة بخطوة."},
    {"id": 40, "name": "مستشار القانون الرقمي", "status": "beta", "kind": "llm", "mode": "professional",
     "instruction": "قدّم معلومات عامة عن التعامل مع المضايقات الرقمية في مصر (مباحث الإنترنت، "
                    "توثيق الأدلة، خطوات البلاغ). وضّح بصراحة إن دي معلومات عامة وليست استشارة قانونية."},
]

BY_ID = {f["id"]: f for f in FEATURES}


def generate_password(length: int = 16) -> str:
    length = max(8, min(64, int(length or 16)))
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*()-_=+[]{}" for c in pw)):
            return pw


def _password_tool(user_input: str) -> str:
    # صيغة الحفظ: label|username|length   أو رقم الطول فقط
    if "|" in user_input:
        parts = [p.strip() for p in user_input.split("|")]
        label = parts[0] or "غير مسمّى"
        username = parts[1] if len(parts) > 1 else ""
        length = int((re.findall(r"\d+", parts[2]) or [16])[0]) if len(parts) > 2 else 16
        pw = generate_password(length)
        database.add_vault_entry(label, username, pw)
        return (f"🔐 اتولّدت واتخزّنت مشفّرة في الخزنة:\n"
                f"الاسم: {label}\nاليوزر: {username}\nكلمة السر: {pw}\n\n"
                "(اعرضها من تبويب الإعدادات > الخزنة لو احتجتها لاحقاً).")
    length = int((re.findall(r"\d+", user_input) or [16])[0])
    return f"🔐 كلمة سر قوية:\n{generate_password(length)}"


def phishing_scan(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return "ابعت الرابط اللي عايز تفحصه."
    reasons, score = [], 0
    low = url.lower()
    if not low.startswith("https://"):
        score += 2; reasons.append("مش بيستخدم HTTPS")
    if re.search(r"https?://\d{1,3}(\.\d{1,3}){3}", low):
        score += 3; reasons.append("بيستخدم IP بدل اسم نطاق")
    if "@" in low.split("//")[-1]:
        score += 3; reasons.append("فيه علامة @ (تمويه الوجهة)")
    if "xn--" in low:
        score += 3; reasons.append("نطاق Punycode (تزييف حروف)")
    host = re.sub(r"^https?://", "", low).split("/")[0]
    if host.count(".") >= 4:
        score += 2; reasons.append("نطاقات فرعية كثيرة مشبوهة")
    if any(host.endswith(t) for t in SUSPICIOUS_TLDS):
        score += 2; reasons.append("امتداد نطاق يكثر فيه الاحتيال")
    if any(s in host for s in SHORTENERS):
        score += 2; reasons.append("رابط مختصر (الوجهة مخفية)")
    if re.search(r"(login|verify|update|secure|account|bank|wallet)", low):
        score += 1; reasons.append("كلمات حسّاسة (login/verify/bank...)")
    verdict = ("🔴 خطر عالٍ — متفتحوش" if score >= 5 else
               "🟡 مشبوه — خد بالك" if score >= 2 else "🟢 يبدو آمناً نسبياً")
    body = "\n".join(f"- {r}" for r in reasons) or "- مفيش علامات تصيّد واضحة"
    return (f"الرابط: {host}\nالتقييم: {verdict} (درجة الخطر {score})\n\nالملاحظات:\n{body}\n\n"
            "ملاحظة: الفحص استدلالي ولا يغني عن الحذر.")


def _vault_tool(user_input: str) -> str:
    parts = [p.strip() for p in user_input.split("|")]
    if len(parts) < 3:
        return "لتخزين سرّ في الخزنة اكتب: «الاسم | اليوزر | السرّ»."
    database.add_vault_entry(parts[0], parts[1], parts[2])
    return f"🔒 اتخزّن «{parts[0]}» مشفّراً في الخزنة المحلية. اعرضه من تبويب الإعدادات."


def run(feature_id: int, user_input: str = "") -> str:
    f = BY_ID.get(feature_id)
    if not f:
        return "ميزة غير موجودة."
    if f["kind"] == "tool":
        if feature_id == 32:
            return _password_tool(user_input)
        if feature_id == 33:
            return phishing_scan(user_input)
        if feature_id == 36:
            return _vault_tool(user_input)
    if f["kind"] == "scaffold":
        return "🔌 " + f.get("note", "تحتاج ربطاً خارجياً.")
    return ai_core.llm(f["instruction"], user_input, f.get("mode", "professional"))
