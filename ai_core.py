"""
ai_core.py — النواة المشتركة: System Prompts مرنة + استدعاء النموذج
Shared core for all advanced modules: a flexible persona system prompt that shifts
tone by task, plus a single OpenRouter LLM helper.

أوضاع الشخصية (mode):
  friendly     → ودّي ومرح بالعامية المصرية (شات العلاقات والسعادة)
  professional → وقور واحترافي جداً (إيميلات، منح، مشاريع، قانوني)
  coach        → مدرّب داعم محفّز
  strict       → صارم وحاسم عند التهاون في الأهداف
"""

import os
import json

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PERSONAS = {
    "friendly": (
        "اتكلم بالعامية المصرية الطبيعية الودودة والذكية، زي صاحب فاهم ومريح، "
        "بخفة دم محترمة وبدون رسمية تقيلة."
    ),
    "professional": (
        "اتكلم بأسلوب وقور واحترافي جداً وواضح ومنظّم. اللغة سليمة ومرتّبة، "
        "ومناسبة للإيميلات الرسمية وطلبات المنح ومشاريع العمل."
    ),
    "coach": (
        "اتكلم كمدرّب تطوير ذات داعم: محفّز، عملي، بيقسّم الكلام لخطوات صغيرة قابلة للتنفيذ."
    ),
    "strict": (
        "اتكلم بحزم محترم ومباشر، بتواجه التهاون والتسويف بصراحة، "
        "وبتطالب بالتزام واضح بالخطوة الجاية."
    ),
}

BASE = ("إنت مساعد ذكي مصري بتفهم الثقافة والسياق المصري كويس جداً، "
        "بترد بدقة وبتدّي قيمة حقيقية وخطوات عملية. ")


def system_prompt(mode: str = "friendly", instruction: str = "") -> str:
    persona = PERSONAS.get(mode, PERSONAS["friendly"])
    extra = f"\nمهمتك تحديداً: {instruction}" if instruction else ""
    return BASE + persona + extra


def has_key() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def llm(instruction: str, user_input: str, mode: str = "friendly",
        temperature: float = 0.7) -> str:
    """استدعاء عام للنموذج بشخصية مرنة. لا يرمي استثناءً."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        return "⚠️ أضف مفتاح OpenRouter في القائمة الجانبية لتشغيل هذه الميزة."
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    messages = [
        {"role": "system", "content": system_prompt(mode, instruction)},
        {"role": "user", "content": user_input.strip() or
         "(المستخدم لم يكتب تفاصيل — اطلب المعلومات الناقصة باختصار وبأدب.)"},
    ]
    try:
        r = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps({"model": model, "messages": messages,
                             "temperature": temperature}),
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(تعذّر التشغيل: {e})"


def stream(messages: list, temperature: float = 0.8):
    """بثّ متعدد الرسائل (للشات المرن)."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        yield "⚠️ أضف مفتاح OpenRouter الأول."
        return
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    payload = {"model": model, "messages": messages, "stream": True,
               "temperature": temperature}
    try:
        with requests.post(OPENROUTER_URL,
                           headers={"Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json"},
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
        yield f"\n\n(تعذّر البثّ: {e})"
