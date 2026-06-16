"""
hyper_scheduler.py — المخطط الصارم وجدول الحركة الدقيق (Hyper-Scheduler)
Dynamic, energy-aware day planner.

- يحلّل منحنى طاقة المستخدم (من يومياته عبر AI، أو منحنى افتراضي ذكي).
- يقسّم اليوم لبلوكات دقيقة، ويوزّع التركيز العميق على أوقات الطاقة العالية،
  والمهام الخفيفة على أوقات الهبوط، ويربط الأهداف الكبرى بأفعال يومية صغيرة.
- يوجّه المستخدم لحظياً: "دلوقتي وقت التركيز على كذا" / "دلوقتي وقت راحة".
"""

import os
import re
import json
from datetime import datetime

import requests

import database

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# منحنى طاقة افتراضي (ساعة اليوم -> مستوى): high / medium / low
DEFAULT_ENERGY = {
    **{str(h): "low" for h in range(0, 7)},
    "7": "medium", "8": "medium", "9": "high", "10": "high", "11": "high",
    "12": "medium", "13": "low", "14": "low", "15": "medium", "16": "high",
    "17": "high", "18": "medium", "19": "medium", "20": "medium",
    "21": "low", "22": "low", "23": "low",
}

BLOCK_MESSAGES = {
    "routine": "🌅 دلوقتي وقت روتين الصباح: تأمل بسيط + راجع أهداف يومك.",
    "focus":   "🎯 دلوقتي وقت التركيز العميق على: {label}",
    "break":   "🌿 دلوقتي وقت راحة: قوم اتحرك، اشرب مياه، بعّد عن الشاشة.",
    "admin":   "🗂️ دلوقتي وقت المهام الخفيفة: ردود، تنظيم، إيميلات.",
    "meal":    "🍽️ دلوقتي وقت الأكل وبريك ذهني.",
    "winddown":"🌙 دلوقتي وقت التهدئة: بعيد عن الشاشات وحضّر نفسك للنوم.",
    "sleep":   "😴 دلوقتي وقت النوم — جسمك محتاج يشحن.",
}


# --------------------------------------------------------------------------
# أدوات الوقت
# --------------------------------------------------------------------------
def _to_min(hhmm: str) -> int:
    h, m = (hhmm.strip().split(":") + ["0"])[:2]
    return int(h) * 60 + int(m)


def _to_hhmm(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def energy_at(minute: int, energy: dict) -> str:
    hour = (minute // 60) % 24
    return (energy or DEFAULT_ENERGY).get(str(hour), "medium")


# --------------------------------------------------------------------------
# تحليل منحنى الطاقة (AI اختياري + fallback)
# --------------------------------------------------------------------------
def analyze_energy_profile(entries_texts: list = None) -> dict:
    """يقدّر منحنى طاقة لـ24 ساعة. يستخدم AI لو المفتاح متاح، وإلا المنحنى الافتراضي."""
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key or not entries_texts:
        return dict(DEFAULT_ENERGY)
    model = os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-chat")
    sample = "\n---\n".join(entries_texts[:8])
    prompt = (
        "حلّل اليوميات التالية وقدّر مستوى طاقة الشخص لكل ساعة من اليوم (0..23). "
        "أعد JSON فقط بهذا الشكل: {\"0\":\"low\",\"9\":\"high\", ...} "
        "بقيم high/medium/low لكل الساعات 0 إلى 23.\n\nاليوميات:\n" + sample
    )
    try:
        r = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps({"model": model, "temperature": 0.2,
                             "response_format": {"type": "json_object"},
                             "messages": [{"role": "user", "content": prompt}]}),
            timeout=90,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.DOTALL)
        data = json.loads(match.group(0) if match else content)
        out = dict(DEFAULT_ENERGY)
        for h in range(24):
            v = str(data.get(str(h), out[str(h)])).lower()
            if v in ("high", "medium", "low"):
                out[str(h)] = v
        return out
    except Exception:
        return dict(DEFAULT_ENERGY)


# --------------------------------------------------------------------------
# بناء الجدول
# --------------------------------------------------------------------------
def build_schedule(goals: list, wake: str = "08:00", sleep: str = "00:00",
                   energy: dict = None) -> list:
    """يبني قائمة بلوكات دقيقة لليوم. كل بلوك: start/end/start_min/end_min/type/label/goal."""
    energy = energy or DEFAULT_ENERGY
    goals = [g.strip() for g in (goals or []) if g.strip()] or ["هدفك الكبير"]
    start = _to_min(wake)
    end = _to_min(sleep)
    if end <= start:
        end += 1440  # النوم بعد منتصف الليل

    plan = []
    cur = start
    gi = 0
    meals_done = {"breakfast": False, "lunch": False, "dinner": False}
    winddown_len = 30

    def add(length, btype, label="", goal=""):
        nonlocal cur
        length = min(length, end - cur)
        if length <= 0:
            return
        plan.append({
            "start": _to_hhmm(cur), "end": _to_hhmm(cur + length),
            "start_min": cur, "end_min": cur + length,
            "type": btype, "label": label, "goal": goal,
        })
        cur += length

    # روتين الصباح ثم الفطار
    add(30, "routine", "روتين الصباح + مراجعة الأهداف")
    if not meals_done["breakfast"]:
        add(20, "meal", "فطار سريع وصحي"); meals_done["breakfast"] = True

    while cur < end - winddown_len:
        # وجبات في أوقاتها
        if not meals_done["lunch"] and (cur % 1440) >= 13 * 60:
            add(45, "meal", "غداء + بريك"); meals_done["lunch"] = True; continue
        if not meals_done["dinner"] and (cur % 1440) >= 20 * 60:
            add(30, "meal", "عشاء خفيف"); meals_done["dinner"] = True; continue

        level = energy_at(cur, energy)
        if level == "high":
            goal = goals[gi % len(goals)]; gi += 1
            add(50, "focus", f"خطوة صغيرة في: {goal}", goal)
            add(10, "break", "راحة قصيرة")
        elif level == "medium":
            goal = goals[gi % len(goals)]; gi += 1
            add(40, "focus", f"تقدّم في: {goal}", goal)
            add(10, "break", "راحة قصيرة")
        else:  # low
            add(40, "admin", "مهام خفيفة/إدارية (ردود، تنظيم)")
            add(15, "break", "راحة أطول / مشية")

    # تهدئة قبل النوم
    add(winddown_len, "winddown", "تهدئة وابتعاد عن الشاشات")
    plan.append({
        "start": _to_hhmm(end), "end": _to_hhmm(end),
        "start_min": end, "end_min": end + 1, "type": "sleep",
        "label": "نوم", "goal": "",
    })
    return plan


# --------------------------------------------------------------------------
# توجيه "الآن"
# --------------------------------------------------------------------------
def now_guidance(plan: list, now: datetime = None) -> dict:
    """يُرجع البلوك الحالي ورسالة توجيه. دالة نقية قابلة للاختبار."""
    now = now or datetime.now()
    t = now.hour * 60 + now.minute
    for block in plan:
        s, e = block["start_min"], block["end_min"]
        for tt in (t, t + 1440):  # معالجة ما بعد منتصف الليل
            if s <= tt < e:
                msg = BLOCK_MESSAGES.get(block["type"], "").format(label=block.get("label", ""))
                return {"active": True, "type": block["type"],
                        "label": block.get("label", ""), "message": msg,
                        "window": f'{block["start"]} - {block["end"]}'}
    return {"active": False, "type": None, "label": "",
            "message": "مفيش بلوك محدد دلوقتي — يا إما وقت نوم يا إما خارج جدول اليوم.",
            "window": ""}


def generate_and_save(goals: list, wake: str, sleep: str,
                      entries_texts: list = None) -> dict:
    """يحلّل الطاقة، يبني الجدول، ويحفظه ليوم اليوم. يُرجع dict الجدول."""
    energy = analyze_energy_profile(entries_texts)
    plan = build_schedule(goals, wake, sleep, energy)
    day = datetime.now().strftime("%Y-%m-%d")
    database.save_schedule(day, plan, goals, energy)
    return {"day": day, "plan": plan, "goals": goals, "energy": energy}


if __name__ == "__main__":
    p = build_schedule(["تعلم بايثون", "مشروع التخرج"], "08:00", "23:30")
    for b in p[:8]:
        print(b["start"], b["end"], b["type"], b["label"])
    print(now_guidance(p))
