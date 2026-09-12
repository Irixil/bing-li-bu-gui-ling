"""真实模型评测：默认严格确定性门槛；仅保留通过 adapter 校验的完整输出。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from . import adapter
from .adapter import Config, organize_event
from .evaluation import evaluate_dataset, passes, safe_endpoint, sha256, write_report


REAL_PROVIDERS = {
    'modelscope': 'ModelScopeProvider', '魔搭': 'ModelScopeProvider',
    'deepseek': 'DeepSeekProvider', 'deepseek-ai': 'DeepSeekProvider',
    'openai_compatible': 'OpenAICompatibleProvider',
    'openai': 'OpenAICompatibleProvider', 'custom': 'OpenAICompatibleProvider',
}
DATASET_PROVENANCE_FIELDS = (
    'dataset_type', 'patient_count', 'source_url', 'doi', 'license', 'license_url',
    'attribution', 'adaptation', 'source_policy',
)
CASE_PROVENANCE_FIELDS = (
    'case_group', 'source_kind', 'source_section', 'limitation',
    'source_url', 'doi', 'license', 'license_url', 'attribution', 'adaptation',
)


def positive_int(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError('--limit 必须为正整数') from None
    if number <= 0:
        raise argparse.ArgumentTypeError('--limit 必须为正整数')
    return number


def _main(argv, *, organize, default_out):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', default='data/synthetic/evaluation.json')
    ap.add_argument('--out', default=default_out)
    ap.add_argument('--limit', type=positive_int, help='仅执行前 N 条；报告保留数据集总量与未执行数量')
    gate = ap.add_mutually_exclusive_group()
    gate.add_argument('--strict', action='store_true', help='严格确定性门槛（默认）')
    gate.add_argument('--smoke', action='store_true', help='只用结构/安全控制退出码；仍报告语义失败')
    args = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    env_file = root / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    try:
        config = Config.from_env()
    except Exception:
        raise SystemExit('拒绝运行：模型配置无效；本次未生成结果') from None
    if config.provider not in REAL_PROVIDERS:
        raise SystemExit('拒绝运行：当前 provider 不是真实模型；Mock 不能冒充真实模型评测')
    if not config.token or not config.model:
        raise SystemExit('拒绝运行：缺少当前 provider 的凭据或模型 ID；本次未生成结果')
    dataset_path = root / args.dataset
    dataset = json.loads(dataset_path.read_text(encoding='utf-8'))
    cases = dataset.get('cases', [])
    if not cases:
        raise SystemExit('拒绝运行：评测集不能为空')
    ids = [case['id'] for case in cases]
    if len(ids) != len(set(ids)):
        raise SystemExit('拒绝运行：完整评测集的 case.id 必须唯一')
    selected = cases[:args.limit] if args.limit is not None else cases
    # This is evaluator ingestion time, never an inferred clinical event time.
    reference_time = dataset.get('reference_time') or datetime.now(timezone.utc).isoformat()
    run_dataset = dict(dataset, cases=selected, reference_time=reference_time)
    # Freeze the checked config, preventing provider switching during a run.
    try:
        provider = adapter.provider_from(config)
    except Exception:
        raise SystemExit('拒绝运行：当前模型配置无法初始化；本次未生成结果') from None
    report = evaluate_dataset(run_dataset, lambda payload: organize(payload, provider),
                              expected_provider=REAL_PROVIDERS[config.provider], capture_output=True)
    for row, case in zip(report['rows'], selected):
        row['provenance'] = {key: case[key] for key in CASE_PROVENANCE_FIELDS if key in case}
        if 'expected_local_danger' in case:
            row['expected_local_danger'] = case['expected_local_danger']
    strict = not args.smoke
    report.update(
        evaluation_type='real_model_regression', provider=config.provider,
        model=config.model, endpoint_origin=safe_endpoint(config.base_url),
        gate='strict_deterministic' if strict else 'schema_safety_smoke',
        gate_pass=passes(report, strict=strict), gate_scope='executed_cases_only',
        dataset_version=dataset.get('dataset_version', dataset.get('version')),
        dataset_sha256=sha256(dataset_path),
        dataset_provenance={key: dataset[key] for key in DATASET_PROVENANCE_FIELDS if key in dataset},
        dataset_case_count=len(cases), executed_case_count=len(selected),
        skipped_case_count=len(cases) - len(selected),
        selection={'method': 'first_n' if args.limit is not None else 'all', 'limit': args.limit,
                   'case_ids': [case['id'] for case in selected]},
        reference_time=reference_time,
        reference_time_source='dataset' if dataset.get('reference_time') else 'evaluation_ingestion_time',
        synthetic_only=dataset.get('source_policy', {}).get('case_data') == 'synthetic',
        prompt_version=adapter.PROMPT_VERSION, prompt_sha256=adapter.PROMPT_SHA256,
        schema_version=adapter.SCHEMA_VERSION,
        output_capture='validated_adapter_output',
        disclaimer='真实模型接口回归；自动门槛仅覆盖已执行条目，完整输出与未执行标签仍需人工复核，不是临床安全结论。',
    )
    if len(selected) != len(cases):
        report['coverage_note'] = f'仅执行 {len(selected)}/{len(cases)} 条，未执行 {len(cases) - len(selected)} 条。' + report['coverage_note']
    write_report(report, root / args.out)
    return 0 if report['gate_pass'] else 1


def main(argv=None):
    return _main(argv, organize=organize_event, default_out='runtime/evaluations/real-result.json')


if __name__ == '__main__':
    raise SystemExit(main())
