"""
wealth_empire.py — مُجمّع إمبراطورية توليد الدخل (150 ميزة)
يوحّد الموديولات الستة في سجل واحد وموزّع تشغيل، ويسجّل كل تشغيل في قاعدة البيانات.

الحالات: 🟢 فعّالة | 🟡 تجريبية | 🔌 تحتاج ربط | ⛔ موقوفة (امتثال/سلامة).
"""

import freelance_empire
import digital_products
import affiliate_radar
import seo_content_factory
import arbitrage_finance
import micro_saas_agency

MODULES = [freelance_empire, digital_products, affiliate_radar,
           seo_content_factory, arbitrage_finance, micro_saas_agency]

STATUS_BADGE = {"active": "🟢 فعّالة", "beta": "🟡 تجريبية",
                "integration": "🔌 تحتاج ربط", "scaffold": "🔌 تحتاج ربط",
                "gated": "⛔ موقوفة (امتثال)"}

_INDEX = {}
for m in MODULES:
    for f in m.FEATURES:
        _INDEX[f["id"]] = (m, f)

ALL_FEATURES = [f for m in MODULES for f in m.FEATURES]


def sections():
    return [{"label": m.SECTION["label"], "key": m.SECTION["key"], "features": m.FEATURES}
            for m in MODULES]


def get_feature(fid):
    e = _INDEX.get(fid)
    return e[1] if e else None


def run_feature(feature_id: int, user_input: str = "") -> dict:
    e = _INDEX.get(feature_id)
    if not e:
        return {"name": "غير معروف", "status": "error", "result": "ميزة غير موجودة."}
    module, feat = e
    try:
        result = module.run(feature_id, user_input)
    except Exception as ex:
        result = f"(خطأ أثناء التشغيل: {ex})"
    try:
        import database
        database.log_feature(feat["id"], feat["name"], feat["status"], str(result)[:300])
    except Exception:
        pass
    return {"name": feat["name"], "status": feat["status"], "result": result}


def counts() -> dict:
    c = {"active": 0, "beta": 0, "integration": 0, "scaffold": 0, "gated": 0}
    for f in ALL_FEATURES:
        c[f["status"]] = c.get(f["status"], 0) + 1
    c["needs_link"] = c.pop("integration", 0) + c.pop("scaffold", 0)
    c["total"] = len(ALL_FEATURES)
    return c


if __name__ == "__main__":
    print("أقسام:", len(MODULES), "| ميزات:", len(ALL_FEATURES))
    print("إحصاء:", counts())
    ids = sorted(f["id"] for f in ALL_FEATURES)
    print("المعرّفات:", ids[0], "..", ids[-1], "| فريدة:", len(set(ids)))
