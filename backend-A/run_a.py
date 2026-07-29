"""
Backend-A 启动入口 — 由 start_all.sh 调用.
用法: python backend-A/run_a.py
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DEEPSEEK_API_KEY', os.environ.get('DEEPSEEK_API_KEY', ''))
import logging; logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%H:%M:%S')
from main import create_app; import uvicorn
app = create_app('config')
uvicorn.run(app, host='0.0.0.0', port=8001, log_level='warning')
