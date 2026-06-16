import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from backend.app import app

if __name__ == "__main__":
    from waitress import serve
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Запуск на http://127.0.0.1:{port}")
    serve(app, host='0.0.0.0', port=port)
