# 🔮 Personal AI Oracle — Docker image (Streamlit + background radar)
FROM python:3.11-slim

# إعدادات بيئة نظيفة
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ORACLE_DB_PATH=/data/oracle.db \
    SCAN_INTERVAL_HOURS=12

WORKDIR /app

# قرص دائم لقاعدة البيانات (يُربط بقرص على Render إن وُجد)
RUN mkdir -p /data

# تثبيت المكتبات أولاً للاستفادة من طبقات الكاش
COPY requirements.txt .
RUN pip install -r requirements.txt

# نسخ بقية الكود
COPY . .

# Streamlit يستمع على المنفذ الذي توفّره المنصّة ($PORT) أو 8501 محلياً
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8501')+'/_stcore/health')" || exit 1

# صيغة shell ليتم توسيع $PORT
CMD streamlit run app.py \
    --server.port=${PORT:-8501} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
