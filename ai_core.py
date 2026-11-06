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

from ai_request import AIRequest
from ai_executor import AIExecutionError, AIExecutor
from llm_provider import OpenRouterProvider, OracleProviderError
from model_router import ModelRouter

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


def _provider(api_key: str | None = None) -> OpenRouterProvider:
    """Return a request-local provider; explicit keys never mutate process env."""
    return OpenRouterProvider(api_key=api_key) if api_key is not None else OpenRouterProvider()


def _router(provider: OpenRouterProvider | None = None) -> ModelRouter:
    """Build a request-local router using optional per-task model configuration."""
    provider = provider or _provider()
    category_env = {
        "fast": "ORACLE_MODEL_FAST",
        "reasoning": "ORACLE_MODEL_REASONING",
        "coding": "ORACLE_MODEL_CODING",
        "research": "ORACLE_MODEL_RESEARCH",
        "writing": "ORACLE_MODEL_WRITING",
        "creative": "ORACLE_MODEL_CREATIVE",
    }
    category_models = {
        task: os.environ[env_name].strip()
        for task, env_name in category_env.items()
        if os.environ.get(env_name, "").strip()
    }
    return ModelRouter(
        default_provider="openrouter",
        default_model=provider.model,
        category_models=category_models,
    )


def _executor(provider: OpenRouterProvider) -> AIExecutor:
    """Build a request-local executor without changing legacy configuration."""
    return AIExecutor(router=_router(provider), provider=provider)


def llm(
    instruction: str,
    user_input: str,
    mode: str = "friendly",
    temperature: float = 0.7,
    *,
    task_type: str | None = None,
    requested_model: str | None = None,
    api_key: str | None = None,
) -> str:
    """استدعاء عام للنموذج بشخصية مرنة. لا يرمي استثناءً."""
    provider = _provider(api_key)
    if not provider.api_key:
        return "⚠️ أضف مفتاح OpenRouter في القائمة الجانبية لتشغيل هذه الميزة."

    request = AIRequest(
        messages=(
            {"role": "system", "content": system_prompt(mode, instruction)},
            {"role": "user", "content": user_input.strip() or
             "(المستخدم لم يكتب تفاصيل — اطلب المعلومات الناقصة باختصار وبأدب.)"},
        ),
        temperature=temperature,
        task_type=task_type,
        requested_model=requested_model,
    )
    try:
        return _executor(provider).execute(request).content
    except OracleProviderError as e:
        return f"(تعذّر التشغيل: {e})"


def stream(
    messages: list,
    temperature: float = 0.8,
    *,
    task_type: str | None = None,
    requested_model: str | None = None,
    api_key: str | None = None,
):
    """بثّ متعدد الرسائل (للشات المرن) عبر مسار التوجيه الموحد."""
    provider = _provider(api_key)
    if not provider.api_key:
        yield "⚠️ أضف مفتاح OpenRouter الأول."
        return

    request = AIRequest(
        messages=tuple(messages),
        temperature=temperature,
        task_type=task_type,
        requested_model=requested_model,
        streaming=True,
    )
    try:
        yield from _executor(provider).execute_stream(request)
    except (OracleProviderError, AIExecutionError) as e:
        yield f"\n\n(تعذّر البثّ: {e})"
