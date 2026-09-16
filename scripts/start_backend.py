"""只启动病历不归零后端 API。"""

from scripts.start_app import main


if __name__ == "__main__":
    raise SystemExit(main())
