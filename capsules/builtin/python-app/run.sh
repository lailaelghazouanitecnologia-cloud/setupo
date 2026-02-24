#!/bin/bash
cd /opt/app
/opt/app/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8080
