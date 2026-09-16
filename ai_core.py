"""
ai_core.py — النواة المشتركة: System Prompts مرنة + طبقة مزوّد LLM
Shared core for all advanced modules: persona prompts plus a provider-backed
OpenRouter LLM helper. Legacy public APIs remain unchanged.

أوضاع الشخصية (mode):
  friendly     → ودّي ومرح بالعامية المصرية (شات العلاقات والسعادة)
  professional → وقور واحترافي جداً (إيميلات، منح، مشاريع، قانوني)
  coach        → مدرّب داعم محفّز
  strict       → صارم وحاسم عند التهاون في الأهداف
"""

import os

from llm_provider import OpenRouterProvider, OracleProviderError

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

# Preserve the original module-level public symbol while keeping the provider
# as the canonical owner of the endpoint configuration.
OPENROUTER_URL = OpenRouterProvider.DEFAULT_URL


def system_prompt(mode: str = "friendly", instruction: str = "") -> str:
    persona = PERSONAS.get(mode, PERSONAS["friendly"])
    extra = f"\nمهمتك تحديداً: {instruction}" if instruction else ""
    return BASE + persona + extra


def has_key() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def _provider() -> OpenRouterProvider:
    """Return the current configured provider without changing legacy config."""
    return OpenRouterProvider()


def llm(instruction: str, user_input: str, mode: str = "friendly",
        temperature: float = 0.7) -> str:
    """استدعاء عام للنموذج بشخصية مرنة. لا يرمي استثناءً."""
    provider = _provider()
    if not provider.api_key:
        return "⚠️ أضف مفتاح OpenRouter في القائمة الجانبية لتشغيل هذه الميزة."

    messages = [
        {"role": "system", "content": system_prompt(mode, instruction)},
        {"role": "user", "content": user_input.strip() or
         "(المستخدم لم يكتب تفاصيل — اطلب المعلومات الناقصة باختصار وبأدب.)"},
    ]
    try:
        return provider.chat(messages, temperature=temperature)
    except OracleProviderError as e:
        return f"(تعذّر التشغيل: {e})"


def stream(messages: list, temperature: float = 0.8):
    """بثّ متعدد الرسائل (للشات المرن)."""
    provider = _provider()
    if not provider.api_key:
        yield "⚠️ أضف مفتاح OpenRouter الأول."
        return
    try:
        yield from provider.stream(messages, temperature=temperature)
    except OracleProviderError as e:
        yield f"\n\n(تعذّر البثّ: {e})"
