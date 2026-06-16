"""
discipline_oracle.py — محراب الانضباط والمستقبل الواقعي
نظام تركيز وانضباط صارم لكنه صحّي:

  • مجلس الحكماء (أرشيتايب إلهام — بدون نسب اقتباسات حرفية لأشخاص حقيقيين).
  • خريطة مستقبل من 4 مستويات (10 سنين / سنة / شهر / يوم بالدقيقة) تُحفظ في قاعدة البيانات.
  • مُنفّذ الكورس اليومي (أمر تركيز قوي — بدون قفل جهازك فعلياً).
  • قائمة حجب المشتتات (تُطبَّق بموافقتك — لا تُعدّل ملفات نظامك تلقائياً).
  • فلتر القيمة (يحجب التفاهات ويُبرز المنح/الفريلانس/الدراسة).
  • محرك سيناريوهات يوتيوب + مسودّات ردود الكومنتات (بمراجعتك).

⚠️ ملاحظة مسؤولة: طُلب أصلاً نظام يدفع لـ«العزوف التام عن النساء والزواج وقمع الشهوة»
ويؤطّرهم كعدوّ. لم نبنِه بهذا الشكل لأنه نظام عزل/تلقين أحادي قد يضرّك ويعمّم سلباً.
بدّلناه بـ«موجّه تركيز صحّي» (sovereign_focus_prompt) يحوّل طاقتك وطموحك نحو هدفك
دون الحطّ من العلاقات أو الزواج أو أي أحد، ودون آليات «إخماد» قسرية.
"""

import os
from datetime import datetime, timedelta

import ai_core
import database

# نطاقات المشتتات الشائعة (للحجب الاختياري بموافقة المستخدم)
DISTRACTION_DOMAINS = [
    "tiktok.com", "www.tiktok.com", "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "youtube.com/shorts", "shorts.youtube.com",
    "reddit.com", "twitter.com", "x.com",
]

VALUE_KEEP = ["منح", "منحة", "scholarship", "grant", "fellowship", "freelance", "فريلانس",
              "مشروع", "course", "كورس", "study", "دراسة", "تمويل", "جامعة", "بحث", "تدريب"]
VALUE_BLOCK = ["سياس", "انتخاب", "مباراة", "كورة", "فضيحة", "شائعة", "مشاهير", "trivia",
               "gossip", "politics", "celebrity"]


# ==========================================================================
# 1) مجلس الحكماء والخريطة الزمنية
# ==========================================================================
def compile_masters_council(situation: str) -> str:
    """مجلس إلهام يدمج أرشيتايبات: الطموح، هوية المنتج، التوسّع الاستراتيجي،
    الانضباط العلمي — ويصيغ توجيهاً يومياً صارماً بلهجة مصرية جدعة (آمرة لا مقترِحة).
    ملاحظة: أرشيتايبات إلهام، ليست اقتباسات حقيقية منسوبة لأشخاص بعينهم."""
    instruction = (
        "إنت «مجلس الحكماء»: تدمج أربع عقليات إلهامية (الطموح والتنفيذ الجريء، هوية "
        "المنتج والتميّز، التوسّع الاستراتيجي والهيبة، الانضباط العلمي والفكري). "
        "ادمج وجهات النظر وأصدر توجيهاً يومياً صارماً وحاداً بلهجة مصرية جدعة وقوية، "
        "بصيغة الأمر لا الاقتراح. كن حازماً ومحفّزاً لكن باحترام — بلا إهانة أو تحقير. "
        "مهم: لا تخترع اقتباسات حرفية منسوبة لأشخاص حقيقيين؛ قدّمها كعقليات إلهام."
    )
    out = ai_core.llm(instruction, situation or "وجّهني النهاردة", mode="strict", temperature=0.7)
    database.add_discipline("توجيه مجلس الحكماء", "issued", out[:200])
    return out


def generate_hyper_realistic_roadmap(goal: str, skills: str = "", save: bool = True) -> dict:
    """يبني خريطة 4 مستويات (10 سنين/سنة/شهر/اليوم) ويحفظها في future_milestones."""
    instruction = (
        "اكتب خريطة طريق واقعية وصارمة من 4 مستويات لهدف المستخدم. لكل مستوى ضع عنواناً "
        "واضحاً و2-4 معالم تنفيذية محددة. ابدأ كل مستوى بسطر بادئته بالضبط:\n"
        "DECADE: ... ثم نقاط\nYEAR: ...\nMONTH: ...\nDAY: ... (جدول اليوم ببلوكات وقت)\n"
        "بلهجة مصرية حازمة وعملية."
    )
    payload = f"الهدف: {goal}\nالمهارات: {skills or '—'}"
    text = ai_core.llm(instruction, payload, mode="coach", temperature=0.6)

    levels = {"decade": "خطة 10 سنين", "year": "خطة السنة",
              "month": "خطة الشهر", "day": "جدول اليوم"}
    if save and text and not text.startswith("⚠️"):
        cur_level = None
        for line in text.splitlines():
            s = line.strip()
            up = s.upper()
            for key in ("DECADE", "YEAR", "MONTH", "DAY"):
                if up.startswith(key + ":"):
                    cur_level = key.lower()
                    title = s.split(":", 1)[1].strip() or levels[cur_level]
                    database.add_milestone(cur_level, levels[cur_level], title)
                    break
            else:
                if cur_level and s.lstrip("-•*0123456789. ").strip():
                    database.add_milestone(cur_level, levels[cur_level],
                                           s.lstrip("-•*0123456789. ").strip()[:120])
    return {"text": text, "saved": save}


def daily_course_enforcer(courses_text: str, start="09:00", end="11:00") -> str:
    """يختار شابتر اليوم من قائمة كورسات يقدّمها المستخدم، ويصدر أمر تركيز تنفيذي.
    (لا يقفل جهازك فعلياً — هذا توجيه تركيز، والقرار قرارك)."""
    lines = [l.strip() for l in (courses_text or "").splitlines() if l.strip()]
    if not lines:
        return ("اكتب قائمة كورساتك (سطر لكل كورس)، ويفضّل بصيغة «اسم الكورس | عدد الشباتر». "
                "وهختارلك شابتر النهاردة وأصدر أمر التركيز.")
    idx = datetime.now().timetuple().tm_yday % len(lines)
    pick = lines[idx]
    name, chapter = pick, "التالي"
    if "|" in pick:
        name, rest = [p.strip() for p in pick.split("|", 1)]
        digits = "".join(ch for ch in rest if ch.isdigit())
        chapter = str((datetime.now().timetuple().tm_yday % max(1, int(digits or 1))) + 1) if digits else "التالي"
    order = (f"🟥 أمر تنفيذي للنهاردة:\n"
             f"هتخلّص شابتر [{chapter}] من كورس [{name}] من الساعة {start} للساعة {end}.\n"
             f"ركّز خالص في البلوك ده، وبعد ما تخلّص أكّد الإنهاء.\n"
             f"— مجلس الانضباط")
    database.add_discipline(f"كورس: {name} شابتر {chapter} ({start}-{end})", "issued")
    return order


# ==========================================================================
# 2) جدار العزل (نسخة آمنة بموافقة المستخدم)
# ==========================================================================
def activate_distraction_blocker(hours: int = 3) -> dict:
    """يولّد قائمة حجب (hosts) للمشتتات لتطبّقها أنت بنفسك — لا يعدّل ملفات نظامك تلقائياً.
    (التعديل التلقائي لملفات النظام/الجدار الناري خطير وقد يعطب الجهاز)."""
    block = "\n".join(f"127.0.0.1 {d}" for d in DISTRACTION_DOMAINS if "/" not in d)
    instructions = (
        "🔒 وضع التركيز — حجب اختياري بموافقتك:\n"
        f"1) افتح ملف الـ hosts (ماك/لينكس: /etc/hosts) بصلاحية مسؤول.\n"
        "2) الصق السطور دي في آخره، واحفظ:\n\n" + block + "\n\n"
        "3) لإلغاء الحجب: امسح نفس السطور.\n"
        f"(يفضّل تفعيله خلال ساعات التطوير الذاتي ~{hours} ساعات).\n"
        "ملاحظة: ده اقتراح تطبّقه بنفسك؛ النظام مش بيعدّل ملفاتك تلقائياً لحمايتك."
    )
    database.add_discipline(f"حجب مشتتات {hours} ساعة (قائمة جاهزة)", "issued")
    return {"hosts_block": block, "instructions": instructions, "domains": DISTRACTION_DOMAINS}


def inbound_value_filtration_loop(items_text: str) -> dict:
    """يفلتر قائمة عناوين/روابط: يُبقي القيمة (منح/فريلانس/دراسة) ويحجب التفاهات."""
    lines = [l.strip() for l in (items_text or "").splitlines() if l.strip()]
    kept, blocked = [], []
    for l in lines:
        low = l.lower()
        if any(b in low for b in VALUE_BLOCK) and not any(k in low for k in VALUE_KEEP):
            blocked.append(l)
        elif any(k in low for k in VALUE_KEEP):
            kept.append(l)
        else:
            kept.append(l)  # غير المصنّف يبقى افتراضياً
    return {"kept": kept, "blocked": blocked,
            "summary": f"احتُفظ بـ{len(kept)} عنصر قيّم، وحُجب {len(blocked)} تافه."}


# ==========================================================================
# 3) إمبراطورية اليوتيوب (سيناريوهات + مسودّات ردود بمراجعتك)
# ==========================================================================
def youtube_trend_scout(niche: str) -> str:
    """يبحث عن أفكار رابحة ويكتب سيناريو فيديو كامل بالعامية + عنوان وتاجز ووصف."""
    trends = ""
    try:
        from search import web_search
        rows = web_search(f"{niche} youtube high rpm video ideas 2026", 5)
        trends = "\n".join(f"- {r['title']}" for r in rows if r.get("title"))
    except Exception:
        trends = ""
    instruction = (
        "اكتب سيناريو فيديو يوتيوب كامل بالعامية المصرية الجذابة في المجال المطلوب. "
        "ابدأ بـ: العنوان، ثم Tags (كلمات مفتاحية)، ثم الوصف، ثم السكربت الكامل "
        "(هوك أول 15 ثانية، النقاط، الخاتمة + CTA)."
    )
    payload = f"المجال: {niche}\nأفكار رائجة (للاستئناس):\n{trends or '—'}"
    script = ai_core.llm(instruction, payload, mode="friendly", temperature=0.85)
    database.add_youtube_log("script", niche, script[:300])
    return script


def youtube_comment_drafts(comments_text: str) -> str:
    """يكتب مسودّات ردود بالعامية على كومنتات تقدّمها — لمراجعتك قبل النشر.
    (الرد الآلي على كل الكومنتات عبر API يخالف الشروط ويُعدّ سبام؛ هنا مسودّات فقط)."""
    comments = [c.strip() for c in (comments_text or "").splitlines() if c.strip()]
    if not comments:
        return "الصق الكومنتات (كومنت في كل سطر) وهكتبلك مسودّات ردود تراجعها."
    instruction = ("اكتب رداً قصيراً لطيفاً وذكياً بالعامية المصرية لكل كومنت، "
                   "بصيغة «الكومنت → الرد». محترم حتى مع الكومنتات السلبية.")
    drafts = ai_core.llm(instruction, "\n".join(comments), mode="friendly")
    database.add_youtube_log("comment_draft", "channel", f"{len(comments)} كومنت")
    return drafts + ("\n\n— ملاحظة: دي مسودّات؛ راجعها وانشرها بنفسك. "
                     "الربط بـ YouTube Data API v3 جاهز كهيكل لكن الرد الآلي على الكل غير مفعّل (سبام).")


# ==========================================================================
# 4) موجّه التركيز الصحّي (بديل صحّي عن نظام العزوف القسري)
# ==========================================================================
def sovereign_focus_prompt(context: str = "") -> str:
    """يبني هوية «الباني الرقمي المستقل» ويحوّل الطاقة والطموح نحو العلم والكود وصيد
    المنح وبناء الثروة — بأسلوب محفّز وحاد، دون الحطّ من العلاقات/الزواج/أي أحد،
    ودون آليات «قمع» قسرية. الانضباط هدف، والعلاقات اختيار شخصي محترم."""
    instruction = (
        "اكتب توجيهاً تحفيزياً صارماً وحاداً بالعامية المصرية يبني هوية «الباني الرقمي "
        "المستقل»: يحوّل طموح المستخدم وطاقته نحو العلم، الكود، صيد المنح، وبناء الثروة. "
        "ركّز على الانضباط، العادات الصحّية (نوم/رياضة/تغذية)، وتوجيه الدافع لأهدافه. "
        "لا تحطّ من العلاقات أو الزواج أو النساء، ولا تصوّرهم كعدوّ، ولا تقترح قمعاً قسرياً "
        "للمشاعر. لو ظهرت إشارات ضيق نفسي، اقترح بلطف التحدث مع شخص موثوق أو مختص."
    )
    out = ai_core.llm(instruction, context or "حفّزني على هدفي", mode="strict", temperature=0.7)
    database.add_discipline("موجّه تركيز", "issued", out[:200])
    return out


def discipline_self_checkin(answers: str = "") -> str:
    """مراجعة يومية صحّية للطاقة والتركيز (بدون أي محتوى تأطيري ضد العلاقات)."""
    instruction = (
        "اعمل مراجعة يومية قصيرة: لو المستخدم كتب إجاباته قيّمها بلطف وحزم واقترح خطوة "
        "تركيز واحدة لبكرة. لو مكتبش حاجة، اسأله 3 أسئلة بسيطة عن طاقته وإنجازه وتشتته."
    )
    return ai_core.llm(instruction, answers, mode="coach")
