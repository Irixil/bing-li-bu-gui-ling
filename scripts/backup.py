"""Create a consistent local SQLite backup, including committed WAL data."""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def backup(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise ValueError('数据库不存在；请先保存至少一条记录')
    if destination.exists():
        raise ValueError('备份目标已存在；请选择新文件名，避免覆盖')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('备份完整性检查失败')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='runtime/records.sqlite3')
    parser.add_argument('--out', default='runtime/backups/records-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    args = parser.parse_args()
    print(backup(args.db, args.out))
