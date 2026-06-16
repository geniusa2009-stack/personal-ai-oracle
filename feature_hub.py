"""
feature_hub.py — مركز الميزات الموحّد (Unified Feature Hub)
يدمج الأنظمة الثلاثة في واجهة واحدة منظّمة وموزّع تشغيل موحّد:

  • core   → features.py            (الوكيل الأساسي، 50 ميزة)
  • super  → advanced_module.py     (الوحدة الخارقة، 50 ميزة)
  • empire → wealth_empire.py       (إمبراطورية الدخل، 150 ميزة)

يوفّر واجهة موحّدة: مجموعات → أقسام → ميزات، مع run() واحد، فيزول التكرار في الكود.
"""

import features as core50
import advanced_module
import wealth_empire


def _core_sections():
    cats = core50.features_by_category()
    return [{"label": core50.CATEGORIES[k], "features": v} for k, v in cats.items()]


GROUPS = [
    {"key": "core", "label": "🧩 الوكيل الأساسي (50)",
     "sections": _core_sections, "run": core50.run_feature,
     "badge": core50.STATUS_BADGE, "counts": core50.counts,
     "desc": "تحليل مشاعر، رادار فرص، مدرب قرار، أولويات، محاكي مقابلات…"},
    {"key": "super", "label": "🛸 الوحدة الخارقة (50)",
     "sections": advanced_module.sections, "run": advanced_module.run_feature,
     "badge": advanced_module.STATUS_BADGE, "counts": advanced_module.counts,
     "desc": "العلاقات، التعلّم الخارق، الذكاء المالي، الأمن السيبراني، أسلوب الحياة."},
    {"key": "empire", "label": "🏛️ إمبراطورية الدخل (150)",
     "sections": wealth_empire.sections, "run": wealth_empire.run_feature,
     "badge": wealth_empire.STATUS_BADGE, "counts": wealth_empire.counts,
     "desc": "فريلانس، منتجات رقمية، أفيليت، SEO، تحكيم مالي، وكالات."},
]

GROUP_BY_KEY = {g["key"]: g for g in GROUPS}
GROUP_BY_LABEL = {g["label"]: g for g in GROUPS}


def normalized_counts(group: dict) -> dict:
    """يوحّد مفاتيح الإحصاء عبر الأنظمة الثلاثة."""
    c = group["counts"]()
    total = c.get("total", 0)
    active = c.get("active", 0)
    beta = c.get("beta", 0)
    other = max(0, total - active - beta)   # تحتاج ربط + موقوفة
    return {"total": total, "active": active, "beta": beta, "other": other}


def grand_total() -> dict:
    out = {"groups": len(GROUPS), "features": 0, "active": 0}
    for g in GROUPS:
        n = normalized_counts(g)
        out["features"] += n["total"]
        out["active"] += n["active"]
    return out


if __name__ == "__main__":
    print("grand total:", grand_total())
    for g in GROUPS:
        print(g["label"], normalized_counts(g),
              "| أقسام:", len(g["sections"]()))
