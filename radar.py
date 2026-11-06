"""
radar.py — رادار الفرص (المهمة الخلفية)
The Opportunity Radar: the background engine that periodically searches the web
for courses, jobs, and grants matching the user's interests, then stores ranked
results in the database.

يُستدعى من:
  - app.py عبر مجدول APScheduler (أثناء عمل الخدمة)
  - worker.py كعملية مستقلة 24/7
"""

import os
import re
import json
from datetime import datetime

import db
import database
import ai_core
from search import web_search

# قوالب الاستعلام لكل فئة (عربي + إنجليزي لتغطية أوسع)
CATEGORY_TEMPLATES = {
    "courses": ["{kw} free online course", "{kw} كورس اونلاين مجاني", "{kw} certification"],
    "jobs":    ["{kw} remote job", "{kw} وظيفة عن بعد", "{kw} hiring 2026"],
    "grants":  ["{kw} grant", "{kw} scholarship", "{kw} منحة دراسية"],
}

CATEGORY_LABELS_AR = {"courses": "كورسات", "jobs": "وظائف", "grants": "منح وفرص"}


# --------------------------------------------------------------------------
# الكلمات المفتاحية النشطة
# --------------------------------------------------------------------------
def active_keywords(limit: int = 8) -> list:
    """يدمج كلمات المستخدم اليدوية + المستخرجة من يومياته الأخيرة."""
    manual_raw = db.get_setting("keywords", "") or ""
    manual = [k.strip() for k in re.split(r"[,\n،]", manual_raw) if k.strip()]
    derived = db.recent_entry_keywords(15)
    merged, seen = [], set()
    for k in manual + derived:
        if k.lower() not in seen:
            seen.add(k.lower())
            merged.append(k)
    return merged[:limit]


# --------------------------------------------------------------------------
# ترتيب النتائج بالذكاء الاصطناعي (اختياري)
# --------------------------------------------------------------------------
def _rank_with_llm(items: list) -> list:
    """Rank opportunity results through the shared AI router using JSON mode."""
    if not ai_core.has_key() or not items:
        return items
    compact = [
        {"i": idx, "title": it["title"], "snippet": it["snippet"], "category": it["category"]}
        for idx, it in enumerate(items[:30])
    ]
    prompt = (
        "أنت مستشار مهني. قيّم مدى قيمة كل فرصة من 0 إلى 100 من حيث الصلة والجدية "
        "والفائدة، واكتب ملخصاً عربياً موجزاً لكل فرصة. لا تعتبر وجود النتيجة دليلاً "
        "على صحتها، ولا تمنح درجة مرتفعة لمجرد صياغة جذابة. "
        "أعد JSON فقط بهذا الشكل: "
        '{"ranked":[{"i":0,"score":50,"summary":"سبب مختصر"}]}\n\n'
        f"الفرص:\n{json.dumps(compact, ensure_ascii=False)}"
    )
    content = ai_core.chat(
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        task_type="research",
        response_format={"type": "json_object"},
        agent_role="researcher",
    )
    try:
        if not content or content.startswith(("⚠️", "(تعذّر")):
            return items
        data = json.loads(content)
        ranked = data.get("ranked", [])
        if not isinstance(ranked, list):
            return items
        for entry in ranked:
            if not isinstance(entry, dict):
                continue
            try:
                index = int(entry.get("i", -1))
                score = int(entry.get("score", 50))
            except (TypeError, ValueError):
                continue
            if 0 <= index < min(30, len(items)):
                items[index]["score"] = max(0, min(100, score))
                summary = entry.get("summary", "")
                items[index]["summary"] = summary.strip()[:500] if isinstance(summary, str) else ""
    except (TypeError, ValueError):
        return items
    return items


# --------------------------------------------------------------------------
# عملية المسح الرئيسية
# --------------------------------------------------------------------------
def run_opportunity_scan(max_per_query: int = 4, use_llm: bool = True, log=print) -> dict:
    """يُشغّل دورة بحث كاملة ويخزّن الفرص الجديدة. يُعيد ملخّص النتيجة."""
    db.init_db()
    keywords = active_keywords()
    if not keywords:
        log("[radar] لا توجد كلمات مفتاحية بعد — أضف اهتماماتك أو اكتب يومية.")
        db.set_setting("last_scan_status", "no_keywords")
        return {"status": "no_keywords", "added": 0, "scanned": 0}

    log(f"[radar] بدء المسح | الكلمات: {keywords}")
    collected, seen_urls = [], set()
    for kw in keywords:
        for category, templates in CATEGORY_TEMPLATES.items():
            for template in templates[:2]:  # قالبان لكل فئة لتقليل عدد الطلبات
                query = template.format(kw=kw)
                for res in web_search(query, max_per_query):
                    url = (res.get("url") or "").strip()
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    collected.append({
                        "found_at": datetime.now().isoformat(timespec="seconds"),
                        "category": category, "keyword": kw,
                        "title": res.get("title", ""), "url": url,
                        "snippet": res.get("snippet", ""),
                        "source": res.get("source", ""), "score": 50, "summary": "",
                    })

    if use_llm:
        collected = _rank_with_llm(collected)

    added = db.add_opportunities(collected)

    # حفظ منح فئة (grants) تلقائياً في جدول المنح المكتشفة
    grants = [{
        "name": it["title"] or it["url"],
        "url": it["url"],
        "requirements": it.get("summary") or it.get("snippet") or "",
        "source": it.get("source", ""),
    } for it in collected if it["category"] == "grants"]
    scholarships_added = database.save_scholarships(grants)

    db.set_setting("last_scan", datetime.now().isoformat(timespec="seconds"))
    db.set_setting("last_scan_status", "ok")
    db.set_setting("last_scan_added", str(added))
    log(f"[radar] انتهى المسح | فحص {len(collected)} نتيجة، أُضيفت {added} فرصة "
        f"و{scholarships_added} منحة جديدة.")
    return {"status": "ok", "added": added, "scanned": len(collected),
            "scholarships_added": scholarships_added, "keywords": keywords}


if __name__ == "__main__":
    print(run_opportunity_scan())
