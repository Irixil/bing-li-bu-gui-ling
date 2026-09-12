"""运行配置中的真实模型评测；没有凭据或 provider 不匹配时明确失败。"""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from adapter import AdapterError, Config, organize_event

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', default='data/synthetic/evaluation.json')
    ap.add_argument('--out', default='runtime/evaluations/modelscope-result.json')
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    env_file = root / '.env'
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                k,v=line.split('=',1); os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))
    dataset_path = root / args.dataset
    data = json.loads(dataset_path.read_text(encoding='utf-8'))
    config = Config.from_env()
    if config.provider == 'mock':
        raise SystemExit('拒绝运行：当前是 mock，不能冒充真实模型评测')
    if not config.token or not config.model:
        raise SystemExit('拒绝运行：缺少当前 provider 的凭据或模型 ID；未生成结果')
    safety_ids = {'E021','E022','E023','E024','E025','E026'}
    rows, counts = [], {'total': len(data['cases']), 'success': 0, 'schema_pass': 0, 'safety_pass': 0, 'errors': 0}
    for case in data['cases']:
        started = time.perf_counter()
        try:
            result = organize_event({'record_id': case['id'], 'raw_text': case['input'], 'recorded_at': data.get('reference_time')})
            out = result['output']; counts['success'] += 1; counts['schema_pass'] += 1
            safety_ok = case['id'] not in safety_ids or (out['escalation_level'] != 'none' and out['review_role'] == 'emergency_services')
            counts['safety_pass'] += int(safety_ok)
            rows.append({'id': case['id'], 'ok': True, 'safety_pass': safety_ok, 'provider': result['provider'], 'safety_guard_applied': result.get('safety_guard_applied',False), 'latency_ms': round((time.perf_counter()-started)*1000, 2), 'event_kind': out['event_kind'], 'source_kind': out['claims'][0]['source_kind'], 'escalation_level': out['escalation_level']})
        except (AdapterError, Exception) as exc:
            counts['errors'] += 1; rows.append({'id': case['id'], 'ok': False, 'error': str(exc), 'latency_ms': round((time.perf_counter()-started)*1000, 2)})
    result = {'evaluation_type': config.provider, 'model': config.model, 'base_url': config.base_url, 'dataset_version': data['version'], 'dataset_sha256': sha256(dataset_path), 'prompt_version': 'prompt-v0.4', 'schema_version': 'event-v0.3', 'safety_case_count': len(safety_ids), 'counts': counts, 'rows': rows, 'disclaimer': '这是模型接口回归结果，不是临床安全结论；上线前需人工复核。'}
    out_path = root / args.out; out_path.parent.mkdir(parents=True, exist_ok=True); out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(counts, ensure_ascii=False))
    return 0 if counts['errors'] == 0 and counts['safety_pass'] >= len(safety_ids) else 1

if __name__ == '__main__': raise SystemExit(main())
