"""
advanced_module.py — وحدة الذكاء الخارق واستشراف المستقبل (المُجمّع)
Sci-Fi Advanced Intelligence / Real-World Operations Module.

يجمع الموديولات الخمسة (50 ميزة) في سجل واحد وموزّع تشغيل موحّد، ويسجّل كل تشغيل
في قاعدة البيانات.
"""

import social_diplomacy
import super_learning
import financial_intelligence
import cyber_security
import lifestyle_hub

MODULES = [social_diplomacy, super_learning, financial_intelligence,
           cyber_security, lifestyle_hub]

# الأقسام الخمسة بالترتيب
SECTIONS = [{"index": i, **m.SECTION, "module": m} for i, m in enumerate(MODULES)]

STATUS_BADGE = {"active": "🟢 فعّالة", "beta": "🟡 تجريبية", "integration": "🔌 تحتاج ربط"}

# خريطة id -> (module, feature)
_INDEX = {}
for m in MODULES:
    for f in m.FEATURES:
        _INDEX[f["id"]] = (m, f)

ALL_FEATURES = [f for m in MODULES for f in m.FEATURES]


def sections():
    """يُرجع الأقسام مع ميزاتها للعرض في الواجهة."""
    return [{"label": m.SECTION["label"], "key": m.SECTION["key"],
             "features": m.FEATURES} for m in MODULES]


def get_feature(feature_id: int):
    entry = _INDEX.get(feature_id)
    return entry[1] if entry else None


def run_feature(feature_id: int, user_input: str = "") -> dict:
    entry = _INDEX.get(feature_id)
    if not entry:
        return {"name": "غير معروف", "status": "error", "result": "ميزة غير موجودة."}
    module, feat = entry
    try:
        result = module.run(feature_id, user_input)
    except Exception as e:
        result = f"(خطأ أثناء التشغيل: {e})"
    try:
        import database
        database.log_feature(feat["id"], feat["name"], feat["status"], str(result)[:300])
    except Exception:
        pass
    return {"name": feat["name"], "status": feat["status"], "result": result}


def counts() -> dict:
    c = {"active": 0, "beta": 0, "integration": 0}
    for f in ALL_FEATURES:
        c[f["status"]] = c.get(f["status"], 0) + 1
    c["total"] = len(ALL_FEATURES)
    return c


if __name__ == "__main__":
    print("الأقسام:", len(SECTIONS), "| إجمالي الميزات:", len(ALL_FEATURES))
    print("الإحصاء:", counts())
    ids = sorted(f["id"] for f in ALL_FEATURES)
    print("المعرّفات:", ids[0], "..", ids[-1], "عدد فريد:", len(set(ids)))
