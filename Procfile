web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true --server.enableCORS=false --server.enableXsrfProtection=false
worker: python worker.py
whatsapp: gunicorn "whatsapp_agent:create_app()" --bind 0.0.0.0:$PORT
