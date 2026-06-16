"""
worker.py — العملية الخلفية المستقلة (24/7)
Standalone background worker that runs the Opportunity Radar on a fixed interval.

استخدمه كـ Background Worker على Render أو خدمة منفصلة على Railway لضمان
عمل البحث التلقائي على مدار الساعة حتى لو لم يفتح أحد التطبيق.

التشغيل:  python worker.py
يعتمد على متغيّرات البيئة:
  OPENROUTER_API_KEY, TAVILY_API_KEY (اختياري), SCAN_INTERVAL_HOURS, ORACLE_DB_PATH
"""

import os
import time
import traceback
from datetime import datetime

import db
import database
import radar


def log(msg: str):
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def main():
    db.init_db()
    database.init_database()
    interval_hours = float(os.environ.get("SCAN_INTERVAL_HOURS", "12"))
    interval_seconds = max(60, int(interval_hours * 3600))
    log(f"🚀 worker بدأ | الفاصل الزمني: كل {interval_hours} ساعة | DB={db.DB_PATH}")

    while True:
        try:
            result = radar.run_opportunity_scan(log=log)
            log(f"✅ نتيجة المسح: {result}")
        except Exception:
            log("❌ خطأ أثناء المسح:\n" + traceback.format_exc())
        log(f"😴 في انتظار الدورة القادمة بعد {interval_hours} ساعة…")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
