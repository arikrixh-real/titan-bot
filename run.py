"""
LEGACY/DEPRECATED ENTRYPOINT.

Official runtime path: titan_daemon.py.
Kept for compatibility only; behavior is intentionally unchanged.
"""

import time
from main import run_once

SCAN_INTERVAL_SECONDS = 120

print("=== TITAN CLOUD MODE STARTED ===")

while True:
    try:
        run_once()
        time.sleep(SCAN_INTERVAL_SECONDS)

    except Exception as e:
        print("Error:", e)
        time.sleep(10)
