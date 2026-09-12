"""离线 Mock：默认结构/安全 smoke；--strict 检查可执行语义及标签冲突。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapter import MockProvider, organize_event
from . import adapter
from .evaluation import evaluate_dataset, passes, sha256, write_report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', default='data/synthetic/evaluation.json')
    ap.add_argument('--out', default='runtime/evaluations/mock-result.json')
    ap.add_argument('--strict', action='store_true', help='可执行语义失败或数据标签冲突时也返回非零')
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    dataset_path = root / args.dataset
    dataset = json.loads(dataset_path.read_text(encoding='utf-8'))
    report = evaluate_dataset(dataset, lambda payload: organize_event(payload, MockProvider()), expected_provider='MockProvider')
    report.update(evaluation_type='offline_mock_smoke', provider='mock', model='mock',
                  gate='strict_deterministic' if args.strict else 'schema_safety_smoke',
                  gate_pass=passes(report, strict=args.strict),
                  dataset_version=dataset.get('version'), dataset_sha256=sha256(dataset_path),
                  synthetic_only=dataset.get('source_policy', {}).get('case_data') == 'synthetic',
                  prompt_version=adapter.PROMPT_VERSION, prompt_sha256=adapter.PROMPT_SHA256,
                  schema_version=adapter.SCHEMA_VERSION,
                  disclaimer='不是任何真实模型结果，不是完整语义通过，也不是临床安全结论。')
    write_report(report, root / args.out)
    return 0 if report['gate_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
