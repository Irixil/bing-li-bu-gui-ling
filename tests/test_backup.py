import pytest
from backend.store import SQLiteStore
from scripts.backup import backup


def test_backup_restores_raw_safety_and_history(tmp_path):
    source = tmp_path / 'source.sqlite3'
    store = SQLiteStore(source)
    event, _ = store.create({'raw_text': '胸闷，喘不上气', 'source_kind': 'elder', 'actor_name': '演示用户'}, 'backup-test')
    store.fail(event['record_id'], 'organize_failed', 'system', {'error': 'simulated_offline'})
    target = backup(source, tmp_path / 'backup.sqlite3')
    recovered = SQLiteStore(target)
    assert recovered.get(event['record_id'])['raw_text'] == event['raw_text']
    assert recovered.get(event['record_id'])['local_safety']['danger_detected']
    assert recovered.history(event['record_id'])[1][-1]['action'] == 'organize_failed'
    with pytest.raises(ValueError):
        backup(source, target)
