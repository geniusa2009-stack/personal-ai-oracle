"""
content_factory.py — مصنع المحتوى الذكي (Content Factory)
يقرأ يوميات المستخدم وأفكاره ويحوّلها إلى محتوى بالعامية المصرية الجذابة
وبنفس أسلوبه الشخصي تماماً، بدون تصنّع.

أنواع المحتوى: منشور فيسبوك، تغريدة/ثريد X، سيناريو فيديو ريلز، كومنت جروب،
كابشن ميمز، نيوزلتر قصير.
"""

import db
import database
import ai_core

CONTENT_TYPES = {
    "منشور فيسبوك": "منشور فيسبوك جذّاب يوقف السكرول، بمقدمة قوية ونهاية فيها سؤال أو دعوة للتفاعل.",
    "تغريدة / ثريد X": "ثريد على X من 3-6 تغريدات مترابطة، كل تغريدة لقطة، بأسلوب قصير ومؤثر.",
    "سيناريو فيديو ريلز": "سيناريو فيديو ريلز/تيك توك (30-45 ثانية): هوك أول 3 ثواني، نقاط، وكول-تو-أكشن.",
    "كومنت جروب": "كومنت قصير ذكي وطبيعي للنشر في جروب نقاش، بدون مبالغة.",
    "كابشن ميمز": "كابشن ميمز مصري خفيف ومضحك مرتبط بالفكرة.",
    "نيوزلتر قصير": "نشرة قصيرة (150-200 كلمة) ودّية وعملية.",
}


def learn_style(max_samples: int = 6) -> str:
    """يجمع عيّنات من كتابة المستخدم الحقيقية من اليوميات لتقليد أسلوبه."""
    try:
        conn = db.get_conn()
        rows = conn.execute(
            "SELECT text FROM entries ORDER BY id DESC LIMIT ?", (max_samples,)
        ).fetchall()
        conn.close()
        return "\n---\n".join(r["text"] for r in rows if r["text"])
    except Exception:
        return ""


def _build_messages(content_type: str, topic: str, style_samples: str):
    spec = CONTENT_TYPES.get(content_type, CONTENT_TYPES["منشور فيسبوك"])
    system = (
        "إنت كاتب محتوى مصري محترف بتكتب بالعامية المصرية الجذّابة والطبيعية جداً. "
        "بتقلّد أسلوب صاحب الحساب بالظبط من عيّنات كتابته (نفس الإيقاع، الكلمات، الطاقة) "
        "من غير تصنّع ومن غير ما تبان إنها مكتوبة بالذكاء الاصطناعي."
    )
    user = (
        (f"عيّنات من أسلوب صاحب الحساب الحقيقي:\n{style_samples}\n\n" if style_samples else "")
        + f"المطلوب: {spec}\n"
        + f"الموضوع/الفكرة: {topic}\n\n"
        + "اكتب المحتوى النهائي جاهز للنشر بالعامية المصرية وبأسلوبه هو."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def stream_content(content_type: str, topic: str):
    """Stream content through the shared AI router/provider pipeline."""
    messages = _build_messages(content_type, topic, learn_style())
    yield from ai_core.stream(messages, temperature=0.9, task_type="creative", agent_role="writer")


def generate_content(content_type: str, topic: str, save: bool = True) -> str:
    """Generate content through AI Core, with optional persistence."""
    if not ai_core.has_key():
        return ""
    messages = _build_messages(content_type, topic, learn_style())
    body = ai_core.chat(messages, temperature=0.9, task_type="creative", agent_role="writer")
    if body and not body.startswith(("⚠️", "(تعذّر")) and save:
        database.save_content(content_type, topic, body)
    return body


if __name__ == "__main__":
    print(generate_content("منشور فيسبوك", "أهمية الاستمرارية في التعلم", save=False))
