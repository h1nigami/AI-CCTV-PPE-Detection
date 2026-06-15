#!/bin/bash
set -e
python3 -u /app/export_models.py
exec python3 -u /app/app.py
