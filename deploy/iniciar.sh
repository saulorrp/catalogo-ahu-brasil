#!/bin/sh
# Sobe a interface web (FastAPI + HTMX). AHU_ROOT_PATH=/ahu serve o app num subcaminho.
exec uvicorn web.main:app --host 0.0.0.0 --port 7860 --proxy-headers --forwarded-allow-ips='*'
