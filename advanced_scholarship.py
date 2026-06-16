"""
advanced_scholarship.py — خبير المنح المطوّر (PS/CV Optimizer + Apex Interview)
أدوات أكاديمية قوية تعتمد على معرفة عامة معروفة بمعايير القبول وأفضل ممارسات الكتابة.

⚠️ أمانة مهنية مدمجة:
  • لا ندّعي «قبول 100%» ولا «معصوم من الخطأ»: القبول يعتمد على عوامل كثيرة خارج النص؛
    مهمتنا رفع الجودة لأعلى مستوى وزيادة فرصك، لا ضمان النتيجة.
  • لا ندّعي «اقتباس 0% مضمون»: نساعد على إعادة صياغة أصيلة وننصح بفحصها بأداة انتحال
    متخصّصة قبل التسليم.
  • قاعدة المعرفة عامة (تيرات/أنماط معروفة) وليست بياناتٍ رسمية لكل جامعة — راجع الموقع الرسمي.
"""

import ai_core

# --------------------------------------------------------------------------
# معرفة أكاديمية عامة (تيرات معروفة) — تُحقن في البرومبتات لرفع جودة التوجيه
# --------------------------------------------------------------------------
ACADEMIC_INTELLIGENCE = {
    "ivy_league": {
        "label": "Ivy League / النخبة الأمريكية",
        "focus": "تميّز أكاديمي + قيادة + أثر مجتمعي + سردية شخصية فريدة (fit مع الجامعة).",
        "essay": "Personal Statement قصصي يربط تجربتك بتخصصك ورؤيتك، صوت أصيل لا مبالغة.",
    },
    "oxbridge": {
        "label": "Oxford / Cambridge",
        "focus": "عمق أكاديمي في التخصص، شغف بحثي واضح، تفكير نقدي.",
        "essay": "Personal Statement أكاديمي مركّز على المادة لا الأنشطة العامة.",
    },
    "mit_stem": {
        "label": "MIT / جامعات STEM",
        "focus": "إنجازات تقنية/بحثية ملموسة، مشاريع، أولمبياد، أثر عملي.",
        "essay": "أمثلة محددة لما بنيته/حللته، شغف بحل المشكلات.",
    },
    "top_global": {
        "label": "أفضل الجامعات عالمياً (Tokyo, ETH, NUS...)",
        "focus": "تفوّق أكاديمي + ملاءمة البرنامج + خطة واضحة بعد التخرج.",
        "essay": "ربط خلفيتك بالبرنامج تحديداً ولماذا هذه الجامعة بالذات.",
    },
    "ib_stem_schools": {
        "label": "الثانويات الدولية (IB / STEM / IGCSE)",
        "focus": "درجات قوية، أنشطة CAS/بحث، توصيات، مقابلة قبول.",
        "essay": "بيان دوافع قصير يُظهر النضج والفضول والالتزام.",
    },
}

ATS_RULES = (
    "قواعد ATS: كلمات مفتاحية من إعلان البرنامج/الوظيفة، صياغة بأفعال إنجاز + أرقام، "
    "تنسيق بسيط بلا جداول/صور معقّدة، عناوين قياسية، ملف نصي قابل للقراءة آلياً."
)


def inject_global_academic_intelligence(target_tier: str = "top_global") -> str:
    """يُرجع كتلة توجيه أكاديمي للتيَر المطلوب لحقنها في البرومبتات."""
    t = ACADEMIC_INTELLIGENCE.get(target_tier, ACADEMIC_INTELLIGENCE["top_global"])
    return (f"[ذكاء أكاديمي — {t['label']}]\n"
            f"معايير التركيز: {t['focus']}\n"
            f"أسلوب المقال: {t['essay']}\n{ATS_RULES}")


# --------------------------------------------------------------------------
# 1) محسّن خطاب النوايا والـ CV
# --------------------------------------------------------------------------
def optimize_personal_statement(draft: str, program: str = "", tier: str = "top_global") -> str:
    intel = inject_global_academic_intelligence(tier)
    instruction = (
        "إنت مستشار قبول جامعي عالمي. راجع خطاب النوايا بصرامة ثم أعد كتابته بنسخة أقوى. "
        f"استرشد بالمعايير دي:\n{intel}\n"
        "اعرض: (أ) نقد صريح لأهم 3 ثغرات، (ب) النسخة المحسّنة كاملة، (ج) نصيحة أخيرة. "
        "كن صادقاً: حسّن الجودة والفرص، وما تَعِدش بقبول مضمون."
    )
    payload = f"البرنامج/الجامعة: {program or '—'}\n\nالمسودّة:\n{draft}"
    return ai_core.llm(instruction, payload, mode="professional", temperature=0.6)


def optimize_cv(cv_text: str, target_role: str = "") -> str:
    instruction = (
        "إنت خبير CV أكاديمي/مهني متوافق مع ATS. راجع السيرة وحسّنها: "
        f"{ATS_RULES}\n"
        "اعرض: أهم الثغرات، ثم نقاط خبرة معاد صياغتها بأفعال إنجاز وأرقام، ثم ترتيب مقترح."
    )
    payload = f"الوظيفة/البرنامج المستهدف: {target_role or '—'}\n\nالسيرة:\n{cv_text}"
    return ai_core.llm(instruction, payload, mode="professional", temperature=0.5)


def originality_rewrite(text: str) -> str:
    """يعيد الصياغة بأسلوب أصيل وينصح بفحص انتحال متخصّص (بلا ادعاء 0% مضمون)."""
    instruction = (
        "أعد صياغة النص بأسلوب أصيل واضح يحافظ على المعنى ويتجنّب النسخ الحرفي. "
        "في الآخر ذكّر المستخدم إن دي خطوة لتحسين الأصالة، ويُفضّل يفحصه بأداة انتحال "
        "متخصّصة قبل التسليم — من غير أي ادعاء بنسبة صفر مضمونة."
    )
    return ai_core.llm(instruction, text, mode="professional", temperature=0.4)


# --------------------------------------------------------------------------
# 2) محاكي المقابلات الشرس (Apex Interview Simulator)
# --------------------------------------------------------------------------
def start_apex_interview(scholarship: str = "Chevening") -> str:
    instruction = (
        "إنت «مفتّش منحة عالمي صارم جداً» بتجري مقابلة بالعامية المصرية الذكية. "
        f"ابدأ مقابلة على نمط أسئلة {scholarship} المعروفة عموماً. اطرح سؤالاً افتتاحياً "
        "تفكيكياً واحداً فقط، وطلب من المستخدم يجاوب. كن جاداً ومحترماً (بلا إهانة)."
    )
    return ai_core.llm(instruction, "ابدأ المقابلة بسؤال واحد قوي.", mode="strict", temperature=0.7)


def apex_interview_turn(scholarship: str, history: str, answer: str) -> str:
    instruction = (
        "إنت مفتّش منحة عالمي صارم. قيّم إجابة المستخدم بصرامة وصدق (بلا تجريح): "
        "اذكر نقاط الضعف بوضوح، ثم اكتب «الصيغة البديلة العبقرية» المثالية للإجابة، "
        "ثم اطرح سؤال فخّ تالي أصعب. كله بالعامية المصرية. "
        f"نمط المنحة: {scholarship}. كن واقعياً وما تَعِدش بقبول مضمون."
    )
    payload = f"سياق المقابلة السابق:\n{history or '(البداية)'}\n\nإجابة المستخدم الآن:\n{answer}"
    return ai_core.llm(instruction, payload, mode="strict", temperature=0.7)


# دالة باسم الطلب الأصلي (واجهة مريحة)
def launch_apex_interview_simulator(scholarship: str = "Chevening",
                                    history: str = "", answer: str = "") -> str:
    if not answer.strip():
        return start_apex_interview(scholarship)
    return apex_interview_turn(scholarship, history, answer)


if __name__ == "__main__":
    print(inject_global_academic_intelligence("oxbridge"))
