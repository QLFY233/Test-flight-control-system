"""
后端 B 入口 — 实时飞控桥 (Python 3.8 + ROS Noetic)。
用法: python main.py --config-dir ../config   (在 backend-B/ 目录下执行)
注意: 目录名 backend-B 含连字符, 不能用 `python -m backend_B.main` 导入 (B-3)。
"""
import sys
import os
import argparse
import logging

# 确保 backend-B/ 在 Python path 中, 支持 backend-B 目录名含连字符的导入
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="后端 B — 实时飞控桥")
    parser.add_argument("--config-dir", default="config", help="配置文件目录 (默认: config)")
    args = parser.parse_args()

    from lifecycle import Lifecycle
    lc = Lifecycle(config_dir=args.config_dir)
    lc.run()


if __name__ == "__main__":
    main()
