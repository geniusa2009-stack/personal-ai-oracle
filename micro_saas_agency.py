"""
micro_saas_agency.py — أتمتة الوكالات والبيزنس المصغّر (الميزات 126-150)
ملاحظة امتثال: كشط خرائط جوجل/فيسبوك للتسويق البارد = كشط بيانات شخصية وسبام (موقوف).
دروب-سيرفيسنج يُبنى كوكالة شفافة (هامش ربح عادي معلَن)، لا خداع.
النسخ الاحتياطي يُصدَّر مشفّراً محلياً وجاهزاً لرفعه بحسابك.
"""

import os
import json
from datetime import datetime

import ai_core
import database

SECTION = {"key": "agency", "label": "🏢 أتمتة الوكالات والبيزنس المصغّر"}


def _f(i, name, status, kind, instruction="", note="", mode="professional"):
    return {"id": i, "name": name, "status": status, "kind": kind,
            "instruction": instruction, "note": note, "mode": mode}


FEATURES = [
    _f(126, "محرّك Drop-Servicing شفّاف", "active", "llm",
       "نظّم استلام مشروع كبير وتقسيمه لمنفّذين بهامش ربح وكالة معلَن وشفّاف، مع ضمان الجودة."),
    _f(127, "موزّع المهام على المنفّذين", "active", "llm", "قسّم المشروع لمهام واضحة قابلة للإسناد."),
    _f(128, "مقيّم جودة التسليم", "active", "llm", "اقترح معايير مراجعة جودة قبل تسليم العميل."),
    _f(129, "حاسبة هامش الوكالة", "active", "llm", "احسب هامش ربح عادل بين سعر العميل وتكلفة المنفّذ."),
    _f(130, "كاتب بريف المنفّذ", "active", "llm", "اكتب بريف واضح للمنفّذ يضمن نتيجة مطابقة لتوقّع العميل."),
    _f(131, "مولّد الفواتير والعقود", "active", "tool",
       "يولّد عقداً/فاتورة احترافية ويحفظها. صيغة: «العميل | المشروع | المبلغ | العملة»."),
    _f(132, "كاتب بنود العقد", "active", "llm",
       "اكتب بنوداً أساسية لعقد خدمة (نطاق، مواعيد، دفع، ملكية، إنهاء). ذكّر إنها ليست استشارة قانونية."),
    _f(133, "كاتب رسالة التحصيل", "active", "llm", "اكتب رسالة تحصيل مهذّبة لمتابعة دفعة متأخّرة."),
    _f(134, "مذكّر استحقاق الدفعات", "beta", "llm", "نظّم تذكيرات مواعيد دفعات العميل."),
    _f(135, "كاتب عرض السعر (Quote)", "active", "llm", "اكتب عرض سعر احترافي مفصّل للعميل."),
    _f(136, "كاشط خرائط جوجل للـ Leads", "gated", "gated",
       note="كشط خرائط جوجل/فيسبوك لجمع بيانات وتسويق بارد = كشط بيانات شخصية وسبام. "
            "البديل: استهدف عملاء لديك إذن/تواصل سابق، وخُد منهم رسالة عرض جاهزة."),
    _f(137, "كاشط صفحات فيسبوك", "gated", "gated",
       note="كشط الصفحات وجمع جهات الاتصال للتسويق البارد ممنوع. استخدم قنوات تسويق مشروعة."),
    _f(138, "كاتب عرض عمل (Warm Outreach)", "active", "llm",
       "اكتب رسالة عرض خدمات مهذّبة لنشاط تجاري وافق على التواصل أو طلب الخدمة (ليست كولد سبام)."),
    _f(139, "محلّل احتياج العميل الرقمي", "active", "llm", "حلّل ما يحتاجه نشاط تجاري رقمياً واقترح خدمة."),
    _f(140, "كاتب دراسة حالة للوكالة", "active", "llm", "اكتب دراسة حالة تعرض نتائجك لإقناع عملاء جدد."),
    _f(141, "كاتب تقرير العميل الدوري", "active", "llm",
       "اكتب تقريراً دورياً مبهجاً يوضّح الإنجاز للعميل لضمان استمرار التعاقد."),
    _f(142, "محلّل رضا العميل", "active", "llm", "اقترح أسئلة قياس رضا العميل وكيفية التصرّف بالنتائج."),
    _f(143, "كاتب رسالة تجديد العقد", "active", "llm", "اكتب رسالة لطيفة لاقتراح تجديد/ترقية العقد الشهري."),
    _f(144, "مقترح خدمات إضافية (Upsell)", "active", "llm", "اقترح خدمات إضافية مناسبة لعميل حالي."),
    _f(145, "مرسل التقارير الآلي", "integration", "scaffold",
       note="الإرسال الآلي للتقارير يحتاج ربط البريد/الواتساب. التقرير نفسه يُكتب الآن جاهزاً."),
    _f(146, "نسخ احتياطي مشفّر", "active", "tool",
       "يصدّر نسخة مشفّرة من بياناتك المالية جاهزة لرفعها لسحابتك."),
    _f(147, "مرحّل لسحابة احتياطية", "integration", "scaffold",
       note="الرفع للسحابة يحتاج مفاتيح تخزينك (S3/Drive). الملف المشفّر يُجهّز محلياً للرفع بيدك."),
    _f(148, "مخطّط استمرارية الأعمال", "active", "llm", "اقترح خطة استمرارية وحماية أصولك الرقمية والمالية."),
    _f(149, "مدقّق أمان الحسابات المالية", "active", "llm", "نصائح لتأمين حساباتك المالية (2FA، تنبيهات...)."),
    _f(150, "زر الطوارئ المالي", "active", "tool",
       "يصدّر نسخة مشفّرة فورية (نفس آلية #146) كإجراء طوارئ لحماية الأصول."),
]

BY_ID = {f["id"]: f for f in FEATURES}


def generate_contract(text: str) -> str:
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 3:
        return "اكتب: «اسم العميل | المشروع | المبلغ | العملة»."
    client, project, amount = parts[0], parts[1], parts[2]
    currency = parts[3] if len(parts) > 3 else "USD"
    body = ai_core.llm(
        "اكتب عقد خدمة/فاتورة احترافية موجزة بالعربية تتضمّن: الأطراف، نطاق العمل، المبلغ، "
        "مواعيد الدفع، حقوق الملكية، وبند الإنهاء. ذكّر في الآخر إنها ليست استشارة قانونية.",
        f"العميل: {client}\nالمشروع: {project}\nالمبلغ: {amount} {currency}",
        mode="professional") if ai_core.has_key() else (
        f"عقد خدمة\nالعميل: {client}\nالمشروع: {project}\nالمبلغ: {amount} {currency}\n"
        "نطاق العمل: ____\nمواعيد الدفع: ____\nالملكية تنتقل بعد السداد الكامل.\n"
        "(نموذج مبدئي — وثّقه قانونياً.)")
    database.add_contract(client, project, amount, currency, "draft", body)
    return body


def secure_backup() -> str:
    """يصدّر نسخة مشفّرة من البيانات المالية الحسّاسة، جاهزة للرفع لسحابتك."""
    data = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "contracts": database.list_contracts(500),
        "revenue_by_stream": database.revenue_by_stream(),
        "affiliate_logs": database.list_affiliate_logs(500),
        "digital_sales": database.list_digital_sales(500),
    }
    blob = json.dumps(data, ensure_ascii=False)
    enc = database._enc(blob)  # تشفير Fernet إن توفّر، وإلا base64
    out_dir = os.environ.get("ORACLE_BACKUP_DIR",
                             os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups"))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"wealth_backup_{datetime.now():%Y%m%d_%H%M%S}.enc")
    with open(path, "w", encoding="utf-8") as f:
        f.write(enc)
    return (f"🔐 اتعملت نسخة احتياطية مشفّرة:\n{path}\n"
            "جاهزة ترفعها لسحابتك (Drive/S3). لفك التشفير لازم نفس مفتاح الخزنة المحلي.")


def run(feature_id: int, user_input: str = "") -> str:
    f = BY_ID.get(feature_id)
    if not f:
        return "ميزة غير موجودة."
    if f["kind"] == "gated":
        return "⛔ موقوف لأسباب امتثال.\n" + f.get("note", "")
    if f["kind"] == "scaffold":
        return "🔌 " + f.get("note", "تحتاج ربطاً خارجياً.")
    if f["kind"] == "tool":
        if feature_id == 131:
            return generate_contract(user_input)
        if feature_id in (146, 150):
            return secure_backup()
    return ai_core.llm(f["instruction"], user_input, f.get("mode", "professional"))
