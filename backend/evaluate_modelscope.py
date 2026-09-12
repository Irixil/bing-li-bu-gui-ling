"""兼容旧命令；真实模型评测的通用入口为 python -m backend.evaluate_real。"""
from .adapter import Config, organize_event
from .evaluate_real import _main


def main(argv=None):
    return _main(argv, organize=organize_event, default_out='runtime/evaluations/modelscope-result.json')


if __name__ == '__main__':
    raise SystemExit(main())
