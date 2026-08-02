"""
Backend-A 启动入口 — 由 start_all.sh 调用.
用法: python backend-A/run_a.py
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DEEPSEEK_API_KEY', os.environ.get('DEEPSEEK_API_KEY', ''))
import logging; logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', datefmt='%H:%M:%S')
from main import create_app; import uvicorn
# I6: INFO 日志 — lifecycle 里程碑/就绪日志必须可见 (原 WARNING 压制全部 INFO,
#     start_all.sh 的 "Application startup complete" 就绪检查必超时)
# I8: 默认绑定回环地址 (防局域网任意对端触发飞控指令); 远程访问设 BACKEND_A_HOST=0.0.0.0
# 端口可用 BACKEND_A_PORT 覆盖 (与 HOST 对称, 供端口冲突/多实例场景)
app = create_app('config')
uvicorn.run(app, host=os.environ.get('BACKEND_A_HOST', '127.0.0.1'),
            port=int(os.environ.get('BACKEND_A_PORT', '8000')), log_level='info')
