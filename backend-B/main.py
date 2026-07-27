"""
后端 B 入口 — 实时飞控桥 (Python 3.8 + ROS Noetic)。
命令行: python -m backend_B.main
"""
import argparse


def main():
    parser = argparse.ArgumentParser(description="后端 B — 实时飞控桥")
    parser.add_argument("--config-dir", default="config", help="配置文件目录")
    args = parser.parse_args()

    # TODO: 阶段B 实现完整生命周期
    print("[backend-B] Starting...")
    print(f"[backend-B] Config dir: {args.config_dir}")
    print("[backend-B] Placeholder — 阶段B 待实现")


if __name__ == "__main__":
    main()
