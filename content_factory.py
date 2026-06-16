"""
content_factory.py — مصنع المحتوى الذكي (Content Factory)
يقرأ يوميات المستخدم وأفكاره ويحوّلها إلى محتوى بالعامية المصرية الجذابة
وبنفس أسلوبه الشخصي تماماً، بدون تصنّع.

أنواع المحتوى: منشور فيسبوك، تغريدة/ثريد X، سيناريو فيديو ريلز، كومنت جروب،
كابشن ميمز، نيوزلتر قصير.
"""

import os
import json

import requests

import db
import database

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

CONTENT_TYPES = {
    "منشور فيسبوك": "منشور فيسبوك جذّاب يوقف السكرول، بمقدمة قوية ونهاية فيها سؤال أو دعوة للتفاعل.",
    "تغريدة / ثريد X": "ثريد على X من 3-6 تغريدات مترابطة، كل تغريدة لقطة، بأسلوب قصير ومؤثر.",
    "سيناريو فيديو ريلز": "سيناريو فيديو ريلز/تيك توك (30-45 ثانية): هوك أول 3 ثواني، نقاط، وكول-تو-أكشن.",
    "كومنت جروب": "كومنت قصير ذكي وطبيعي للنشر في جروب نقاش، بدون مبالغة.",
    "كابشن ميمز": "كابشن ميمز مصري خفيف ومضحك مرتبط بالفكرة.",
    "نيوزلتر قصير": "نشرة قصيرة (150-200 كلمة) ودّية وعملية.",
}


def _headers(key):
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


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
    """مولّد بثّ كلمة بكلمة لعرضه فورياً في الواجهة."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        yield "⚠️ أضف مفتاح OpenRouter الأول."
        return
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    messages = _build_messages(content_type, topic, learn_style())
    payload = {"model": model, "messages": messages, "stream": True, "temperature": 0.9}
    try:
        with requests.post(OPENROUTER_URL, headers=_headers(key),
                           data=json.dumps(payload), stream=True, timeout=180) as resp:
            resp.raise_for_status()
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore")
                if not line.startswith("data: "):
                    continue
                chunk = line[6:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    delta = json.loads(chunk)["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                except Exception:
                    continue
    except Exception as e:
        yield f"\n\n(تعذّر التوليد: {e})"


def generate_content(content_type: str, topic: str, save: bool = True) -> str:
    """توليد غير متدفّق (للاستخدام الخلفي/البرمجي)، مع حفظ اختياري."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return ""
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    messages = _build_messages(content_type, topic, learn_style())
    try:
        r = requests.post(OPENROUTER_URL, headers=_headers(key),
                          data=json.dumps({"model": model, "messages": messages,
                                           "temperature": 0.9}), timeout=180)
        r.raise_for_status()
        body = r.json()["choices"][0]["message"]["content"].strip()
        if save and body:
            database.save_content(content_type, topic, body)
        return body
    except Exception as e:
        return f"(تعذّر التوليد: {e})"


if __name__ == "__main__":
    print(generate_content("منشور فيسبوك", "أهمية الاستمرارية في التعلم", save=False))
