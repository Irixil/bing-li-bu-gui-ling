"""Durable, versioned state transitions for one local household.

Every mutating operation is a short SQLite transaction. Model/network work stays
outside these transactions; organize() compares the version again at commit.
Family review acknowledges record accuracy and cannot clear clinical concerns.
"""
from __future__ import annotations

import hashlib
import base64
import hmac
import json
import math
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix=''):
    return prefix + str(uuid.uuid4())


try:
    from .safety import scan_danger
except ImportError:
    from safety import scan_danger

class StoreError(RuntimeError):
    status = 400


class NotFound(StoreError):
    status = 404


class Conflict(StoreError):
    status = 409


class Unauthorized(StoreError):
    status = 401


class Forbidden(StoreError):
    status = 403


SOURCES = {
    'elder', 'family_observation', 'family_report', 'caregiver',
    'clinician_evidence', 'document', 'audio_transcript', 'system', 'unknown',
}
SNAPSHOT_FIELDS = (
    'record_id', 'raw_text', 'source_kind', 'actor_name', 'occurred_time',
    'recorded_at', 'state', 'version', 'draft', 'result_meta', 'review_notes',
    'local_safety',
    'related_record_ids', 'supersedes_id', 'confirmation_scope',
)


def expected_version(value):
    # bool is an int subclass; it must never count as version 1.
    if type(value) is not int or value < 1:
        raise StoreError('expected_version_must_positive_integer')
    return value


def text_field(value, name, maximum, required=True):
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise StoreError(name + '_required')
    if len(value) > maximum:
        raise StoreError(name + '_too_long')
    return value


class SQLiteStore:
    # Local transition defaults.  These values are deliberately explicit so a
    # later PostgreSQL service can carry the same account policy forward.
    PASSWORD_ALGORITHM = 'pbkdf2_sha256'
    PASSWORD_ITERATIONS = 310_000
    PASSWORD_SALT_BYTES = 16
    MAX_LOGIN_FAILURES = 5
    LOCKOUT_SECONDS = 15 * 60

    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.init()

    def conn(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('PRAGMA busy_timeout=10000')
            return c
        except BaseException:
            c.close()
            raise

    @contextmanager
    def connection(self):
        c = self.conn()
        try:
            yield c
        except BaseException:
            if c.in_transaction:
                c.rollback()
            raise
        finally:
            c.close()

    @contextmanager
    def transaction(self):
        # BEGIN IMMEDIATE also serializes writers from separate processes or
        # distinct Store instances; the Python lock alone is insufficient.
        with self.lock, self.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()

    def init(self):
        with self.lock, self.connection() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''
                CREATE TABLE IF NOT EXISTS events (
                    record_id TEXT PRIMARY KEY,
                    raw_text TEXT NOT NULL, source_kind TEXT NOT NULL,
                    actor_name TEXT NOT NULL, occurred_time TEXT,
                    recorded_at TEXT NOT NULL, state TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1, draft_json TEXT,
                    result_meta_json TEXT, review_notes TEXT,
                    related_record_ids_json TEXT, supersedes_id TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(supersedes_id) REFERENCES events(record_id)
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    revision_id TEXT PRIMARY KEY, record_id TEXT NOT NULL,
                    action TEXT NOT NULL, version INTEGER NOT NULL,
                    snapshot_json TEXT NOT NULL, actor_name TEXT, at TEXT NOT NULL,
                    FOREIGN KEY(record_id) REFERENCES events(record_id)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    audit_id TEXT PRIMARY KEY, record_id TEXT, action TEXT NOT NULL,
                    version INTEGER, actor_name TEXT, at TEXT NOT NULL,
                    details_json TEXT
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    idem_key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    FOREIGN KEY(record_id) REFERENCES events(record_id)
                );
                CREATE TABLE IF NOT EXISTS handoffs (
                    handoff_id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    household_id TEXT
                );
                CREATE TABLE IF NOT EXISTS households (
                    household_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
                    external_key TEXT UNIQUE, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS household_members (
                    household_id TEXT NOT NULL, user_id TEXT NOT NULL,
                    role TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (household_id, user_id),
                    FOREIGN KEY(household_id) REFERENCES households(household_id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    household_id TEXT NOT NULL, expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL, revoked_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(user_id),
                    FOREIGN KEY(household_id) REFERENCES households(household_id)
                );
                CREATE INDEX IF NOT EXISTS session_expiry ON sessions(expires_at);
                CREATE UNIQUE INDEX IF NOT EXISTS one_revision_per_version
                    ON revisions(record_id, version);
                CREATE UNIQUE INDEX IF NOT EXISTS one_replacement_per_event
                    ON events(supersedes_id) WHERE supersedes_id IS NOT NULL;
                CREATE INDEX IF NOT EXISTS event_creation_order
                    ON events(recorded_at, created_at);
                CREATE INDEX IF NOT EXISTS audit_event_order
                    ON audit(record_id, at);
                CREATE TRIGGER IF NOT EXISTS preserve_event_evidence
                BEFORE UPDATE OF raw_text, source_kind, actor_name, occurred_time,
                    recorded_at, related_record_ids_json, supersedes_id, created_at
                ON events BEGIN
                    SELECT RAISE(ABORT, 'event_evidence_immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS preserve_revision_update
                BEFORE UPDATE ON revisions BEGIN
                    SELECT RAISE(ABORT, 'revision_immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS preserve_revision_delete
                BEFORE DELETE ON revisions BEGIN
                    SELECT RAISE(ABORT, 'revision_immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS preserve_audit_update
                BEFORE UPDATE ON audit BEGIN
                    SELECT RAISE(ABORT, 'audit_immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS preserve_audit_delete
                BEFORE DELETE ON audit BEGIN
                    SELECT RAISE(ABORT, 'audit_immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS preserve_handoff_update
                BEFORE UPDATE ON handoffs BEGIN
                    SELECT RAISE(ABORT, 'handoff_immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS preserve_handoff_delete
                BEFORE DELETE ON handoffs BEGIN
                    SELECT RAISE(ABORT, 'handoff_immutable');
                END;
            ''')
            # Existing databases predate household ownership. Add the nullable
            # column and attach old records to a deterministic local household.
            cols = {r['name'] for r in c.execute('PRAGMA table_info(events)')}
            if 'safety_json' not in cols:
                c.execute('ALTER TABLE events ADD COLUMN safety_json TEXT')
            if 'household_id' not in cols:
                c.execute('ALTER TABLE events ADD COLUMN household_id TEXT')
            # Account credentials were added after the first local auth
            # prototype.  Migrate in place and never store a raw password.
            user_cols = {r['name'] for r in c.execute('PRAGMA table_info(users)')}
            migrations = (
                ('password_hash', 'TEXT'),
                ('password_salt', 'TEXT'),
                ('password_iterations', 'INTEGER NOT NULL DEFAULT 0'),
                ('password_algorithm', "TEXT NOT NULL DEFAULT 'legacy'"),
                ('failed_attempts', 'INTEGER NOT NULL DEFAULT 0'),
                ('locked_until', 'TEXT'),
                ('last_login_at', 'TEXT'),
            )
            for column, declaration in migrations:
                if column not in user_cols:
                    c.execute(f'ALTER TABLE users ADD COLUMN {column} {declaration}')
            if c.execute("SELECT 1 FROM households WHERE household_id='hh_local_default'").fetchone() is None:
                at = now(); hid = 'hh_local_default'; uid0 = 'usr_local_default'
                c.execute('INSERT OR IGNORE INTO households VALUES(?,?,?)', (hid, '本地默认家庭', at))
                c.execute('''INSERT OR IGNORE INTO users(
                    user_id,display_name,external_key,created_at,password_hash,password_salt,
                    password_iterations,password_algorithm,failed_attempts,locked_until,last_login_at
                ) VALUES(?,?,?,?,NULL,NULL,0,'legacy',0,NULL,NULL)''',
                          (uid0, '本地用户', 'local-default', at))
                c.execute('INSERT OR IGNORE INTO household_members VALUES(?,?,?,?,?)', (hid, uid0, 'owner', 'active', at))
            c.execute("UPDATE events SET household_id='hh_local_default' WHERE household_id IS NULL")
            hcols = {r['name'] for r in c.execute('PRAGMA table_info(handoffs)')}
            if 'household_id' not in hcols:
                c.execute('ALTER TABLE handoffs ADD COLUMN household_id TEXT')

    @staticmethod
    def dec(row):
        if row is None:
            return None
        event = dict(row)
        for db_field, field in (
            ('draft_json', 'draft'), ('result_meta_json', 'result_meta'),
            ('related_record_ids_json', 'related_record_ids'),
        ):
            raw = event.pop(db_field, None)
            event[field] = json.loads(raw) if raw else ([] if field == 'related_record_ids' else None)
        saved_safety = event.pop('safety_json', None)
        event['local_safety'] = json.loads(saved_safety) if saved_safety else scan_danger(event['raw_text'])
        event['confirmation_scope'] = 'record_accuracy' if event['state'] == 'recorded' else None
        return event

    @staticmethod
    def snap(event):
        return {k: event.get(k) for k in SNAPSHOT_FIELDS}

    def rev(self, c, event, action, actor):
        c.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)', (
            uid('rev_'), event['record_id'], action, event['version'],
            json.dumps(self.snap(event), ensure_ascii=False), actor, now(),
        ))

    def aud(self, c, rid, action, version, actor, details=None):
        c.execute('INSERT INTO audit VALUES(?,?,?,?,?,?,?)', (
            uid('aud_'), rid, action, version, actor, now(),
            json.dumps(details or {}, ensure_ascii=False),
        ))

    @staticmethod
    def exists(c, rid):
        return c.execute('SELECT 1 FROM events WHERE record_id=?', (rid,)).fetchone() is not None

    def _get(self, c, rid):
        event = self.dec(c.execute('SELECT * FROM events WHERE record_id=?', (rid,)).fetchone())
        if event is None:
            raise NotFound('event_not_found')
        return event

    def _versioned(self, c, rid, expected):
        event = self._get(c, rid)
        if event['version'] != expected:
            raise Conflict('stale_version')
        return event

    @staticmethod
    def _payload(payload):
        if not isinstance(payload, dict):
            raise StoreError('body_must_object')
        if 'recorded_at' in payload:
            raise StoreError('recorded_at_read_only')
        text_field(payload.get('raw_text'), 'raw_text', 10000)
        text_field(payload.get('source_kind'), 'source_kind', 40)
        if payload['source_kind'] not in SOURCES:
            raise StoreError('invalid_source_kind')
        text_field(payload.get('actor_name'), 'actor_name', 80)
        text_field(payload.get('occurred_time'), 'occurred_time', 120, required=False)
        related = payload.get('related_record_ids', [])
        if not isinstance(related, list) or len(related) > 10:
            raise StoreError('related_record_ids_must_bounded_list')
        if any(not isinstance(r, str) or not r or len(r) > 80 for r in related):
            raise StoreError('invalid_related_record_id')
        if len(related) != len(set(related)):
            raise StoreError('duplicate_related_record_id')
        return related

    def _insert(self, c, payload, related, supersedes_id=None, reason=None):
        at = now()
        rid = uid('rec_')
        c.execute('''INSERT INTO events
            (record_id,raw_text,source_kind,actor_name,occurred_time,recorded_at,
             state,version,draft_json,result_meta_json,review_notes,
             related_record_ids_json,supersedes_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            rid, payload['raw_text'], payload['source_kind'], payload['actor_name'],
            payload.get('occurred_time'), at,
            'inbox', 1, None, None, reason, json.dumps(related), supersedes_id, at, at,
        ))
        safety = scan_danger(payload['raw_text'])
        c.execute('UPDATE events SET safety_json=? WHERE record_id=?', (json.dumps(safety, ensure_ascii=False), rid))
        return self._get(c, rid)

    def get(self, rid, household_id=None):
        with self.connection() as c:
            if household_id:
                return self.dec(c.execute('SELECT * FROM events WHERE record_id=? AND household_id=?', (rid, household_id)).fetchone())
            return self.dec(c.execute('SELECT * FROM events WHERE record_id=?', (rid,)).fetchone())

    def list(self, household_id=None):
        with self.connection() as c:
            if household_id:
                return [self.dec(r) for r in c.execute('SELECT * FROM events WHERE household_id=? ORDER BY recorded_at,created_at,record_id', (household_id,))]
            return [self.dec(r) for r in c.execute('SELECT * FROM events ORDER BY recorded_at,created_at,record_id')]

    def create(self, payload, key, actor='system', household_id='hh_local_default'):
        # Legacy callers may omit household_id; account-aware callers pass the
        # authenticated household explicitly and are checked by the API layer.
        text_field(household_id, 'household_id', 100)
        related = self._payload(payload)
        text_field(key, 'idempotency_key', 200)
        text_field(actor, 'actor_name', 80)
        try:
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise StoreError('invalid_json_payload') from exc
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.transaction() as c:
            prior = c.execute('SELECT * FROM idempotency WHERE idem_key=?', (key,)).fetchone()
            if prior:
                if prior['payload_hash'] != digest:
                    raise Conflict('idempotency_key_payload_mismatch')
                return self._get(c, prior['record_id']), False
            for r in related:
                rr = c.execute('SELECT household_id FROM events WHERE record_id=?', (r,)).fetchone()
                if rr is None: raise NotFound('related_record_not_found')
                if rr['household_id'] not in (None, household_id): raise Forbidden('cross_household_reference_denied')
            event = self._insert(c, payload, related)
            c.execute('UPDATE events SET household_id=? WHERE record_id=?', (household_id, event['record_id']))
            event['household_id'] = household_id
            self.rev(c, event, 'created', actor)
            self.aud(c, event['record_id'], 'created', 1, actor, {'idempotency_key': key})
            c.execute('INSERT INTO idempotency VALUES(?,?,?)', (key, digest, event['record_id']))
            return event, True

    # --- Household identity and authorization (local SQLite transition layer) ---
    ROLES = {'owner', 'elder', 'family', 'caregiver', 'clinician'}
    PERMISSIONS = {
        'read': {'owner', 'elder', 'family', 'caregiver', 'clinician'},
        'create': {'owner', 'elder', 'family', 'caregiver'},
        'organize': {'owner', 'family', 'caregiver', 'clinician'},
        'review': {'owner', 'elder', 'family', 'caregiver', 'clinician'},
        'revise': {'owner', 'family', 'caregiver'},
        'export': {'owner', 'family', 'caregiver', 'clinician'},
        'manage_members': {'owner'},
    }

    @staticmethod
    def _hash_token(token):
        return hashlib.sha256(str(token).encode()).hexdigest()

    def _auth_audit(self, c, action, user_id=None, household_id=None, details=None):
        self.aud(c, None, action, None, user_id or 'system', {
            'household_id': household_id, **(details or {})
        })

    @classmethod
    def _password_record(cls, password):
        if password is None:
            return (None, None, 0, 'legacy')
        password = text_field(password, 'password', 256)
        if len(password) < 8:
            raise StoreError('password_too_short')
        salt = secrets.token_bytes(cls.PASSWORD_SALT_BYTES)
        digest = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), salt, cls.PASSWORD_ITERATIONS,
        )
        return (
            base64.b64encode(digest).decode('ascii'),
            base64.b64encode(salt).decode('ascii'),
            cls.PASSWORD_ITERATIONS,
            cls.PASSWORD_ALGORITHM,
        )

    @classmethod
    def _verify_password(cls, password, row):
        if not row['password_hash'] or row['password_algorithm'] == 'legacy':
            # Existing local accounts are intentionally kept usable during
            # migration.  New accounts should always pass a password.
            return password is None
        if not isinstance(password, str):
            return False
        try:
            salt = base64.b64decode(row['password_salt'], validate=True)
            expected = base64.b64decode(row['password_hash'], validate=True)
            actual = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'), salt,
                int(row['password_iterations'] or cls.PASSWORD_ITERATIONS),
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(actual, expected)

    def create_household(self, name, display_name, role='owner', external_key=None, password=None):
        name = text_field(name, 'household_name', 120)
        display_name = text_field(display_name, 'display_name', 80)
        if role not in self.ROLES: raise StoreError('invalid_role')
        password_hash, password_salt, password_iterations, password_algorithm = self._password_record(password)
        at = now(); hid, user_id = uid('hh_'), uid('usr_')
        with self.transaction() as c:
            c.execute('INSERT INTO households VALUES(?,?,?)', (hid, name, at))
            c.execute('''INSERT INTO users(
                user_id,display_name,external_key,created_at,password_hash,password_salt,
                password_iterations,password_algorithm,failed_attempts,locked_until,last_login_at
            ) VALUES(?,?,?,?,?,?,?,?,0,NULL,NULL)''', (
                user_id, display_name, external_key, at, password_hash, password_salt,
                password_iterations, password_algorithm,
            ))
            c.execute('INSERT INTO household_members VALUES(?,?,?,?,?)', (hid, user_id, role, 'active', at))
            self._auth_audit(c, 'household_created', user_id, hid, {'role': role})
        return {'household_id': hid, 'name': name, 'user_id': user_id, 'display_name': display_name, 'role': role}

    def add_member(self, household_id, display_name, role='family', external_key=None, password=None):
        text_field(household_id, 'household_id', 100); display_name = text_field(display_name, 'display_name', 80)
        if role not in self.ROLES: raise StoreError('invalid_role')
        password_hash, password_salt, password_iterations, password_algorithm = self._password_record(password)
        at = now(); user_id = uid('usr_')
        with self.transaction() as c:
            if c.execute('SELECT 1 FROM households WHERE household_id=?', (household_id,)).fetchone() is None: raise NotFound('household_not_found')
            c.execute('''INSERT INTO users(
                user_id,display_name,external_key,created_at,password_hash,password_salt,
                password_iterations,password_algorithm,failed_attempts,locked_until,last_login_at
            ) VALUES(?,?,?,?,?,?,?,?,0,NULL,NULL)''', (
                user_id, display_name, external_key, at, password_hash, password_salt,
                password_iterations, password_algorithm,
            ))
            c.execute('INSERT INTO household_members VALUES(?,?,?,?,?)', (household_id, user_id, role, 'active', at))
            self._auth_audit(c, 'member_added', user_id, household_id, {'role': role})
        return {'user_id': user_id, 'display_name': display_name, 'household_id': household_id, 'role': role, 'status': 'active'}

    def list_members(self, household_id):
        with self.connection() as c:
            return [dict(r) for r in c.execute('''SELECT u.user_id,u.display_name,u.external_key,
                m.household_id,m.role,m.status,m.created_at FROM household_members m
                JOIN users u ON u.user_id=m.user_id WHERE m.household_id=? ORDER BY m.created_at''', (household_id,))]

    def login(self, user_id=None, display_name=None, household_id=None, ttl_seconds=86400, password=None):
        if not user_id and not display_name: raise StoreError('user_id_or_display_name_required')
        if type(ttl_seconds) is not int or ttl_seconds <= 0 or ttl_seconds > 30 * 86400:
            raise StoreError('invalid_session_ttl')
        with self.transaction() as c:
            q = '''SELECT m.*,u.display_name,u.password_hash,u.password_salt,
                u.password_iterations,u.password_algorithm,u.failed_attempts,u.locked_until,
                u.last_login_at FROM household_members m JOIN users u ON u.user_id=m.user_id
                WHERE m.status='active' '''
            args = []
            if user_id: q += ' AND m.user_id=?'; args.append(user_id)
            else: q += ' AND u.display_name=?'; args.append(display_name)
            if household_id: q += ' AND m.household_id=?'; args.append(household_id)
            row = c.execute(q + ' LIMIT 1', args).fetchone()
            if row is None: raise Unauthorized('invalid_credentials')
            current = datetime.now(timezone.utc)
            if row['locked_until'] and row['locked_until'] > current.isoformat():
                self._auth_audit(c, 'login_locked', row['user_id'], row['household_id'], {
                    'failed_attempts': row['failed_attempts'] or 0,
                })
                # The transaction context rolls back when an exception leaves
                # the block.  Commit the audit before returning the auth error.
                c.commit()
                raise Unauthorized('account_locked')
            if not self._verify_password(password, row):
                failures = int(row['failed_attempts'] or 0) + 1
                locked_until = None
                if failures >= self.MAX_LOGIN_FAILURES:
                    locked_until = datetime.fromtimestamp(
                        current.timestamp() + self.LOCKOUT_SECONDS, timezone.utc,
                    ).isoformat()
                c.execute('''UPDATE users SET failed_attempts=?,locked_until=? WHERE user_id=?''',
                          (failures, locked_until, row['user_id']))
                self._auth_audit(c, 'login_failed', row['user_id'], row['household_id'], {
                    'failed_attempts': failures, 'locked': bool(locked_until),
                })
                c.commit()
                raise Unauthorized('account_locked' if locked_until else 'invalid_credentials')
            token = secrets.token_urlsafe(32); at = now(); exp = datetime.fromtimestamp(current.timestamp()+ttl_seconds, timezone.utc).isoformat()
            c.execute('''UPDATE users SET failed_attempts=0,locked_until=NULL,last_login_at=?
                WHERE user_id=?''', (at, row['user_id']))
            c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,NULL)', (self._hash_token(token), row['user_id'], row['household_id'], exp, at))
            self._auth_audit(c, 'login', row['user_id'], row['household_id'])
            return {'token': token, 'expires_at': exp, 'user_id': row['user_id'], 'household_id': row['household_id'], 'role': row['role'], 'display_name': row['display_name']}

    def authenticate(self, token):
        if not token: raise Unauthorized('auth_token_required')
        with self.connection() as c:
            row = c.execute('''SELECT s.*,u.display_name,m.role FROM sessions s
                JOIN users u ON u.user_id=s.user_id JOIN household_members m
                ON m.user_id=s.user_id AND m.household_id=s.household_id
                WHERE s.token_hash=? AND s.revoked_at IS NULL''', (self._hash_token(token),)).fetchone()
            if row is None: raise Unauthorized('invalid_session')
            if row['expires_at'] <= now(): raise Unauthorized('session_expired')
            return dict(row)

    def revoke_session(self, token):
        with self.transaction() as c:
            row = c.execute('SELECT user_id,household_id FROM sessions WHERE token_hash=?', (self._hash_token(token),)).fetchone()
            if row: c.execute('UPDATE sessions SET revoked_at=? WHERE token_hash=?', (now(), self._hash_token(token)))
            if row: self._auth_audit(c, 'logout', row['user_id'], row['household_id'])

    def authorize(self, token, permission, household_id=None):
        ctx = self.authenticate(token)
        if household_id and ctx['household_id'] != household_id: raise Forbidden('household_access_denied')
        if permission not in self.PERMISSIONS or ctx['role'] not in self.PERMISSIONS[permission]: raise Forbidden('permission_denied')
        return ctx

    def history(self, rid):
        with self.connection() as c:
            # A read transaction ensures the history and audit share one snapshot.
            c.execute('BEGIN')
            self._get(c, rid)
            history = []
            for row in c.execute('SELECT * FROM revisions WHERE record_id=? ORDER BY version,at', (rid,)):
                item = dict(row)
                item['snapshot'] = json.loads(item.pop('snapshot_json'))
                history.append(item)
            audit = []
            for row in c.execute('SELECT * FROM audit WHERE record_id=? ORDER BY at,audit_id', (rid,)):
                item = dict(row)
                item['details'] = json.loads(item.pop('details_json') or '{}')
                audit.append(item)
            return history, audit

    def organize(self, rid, expected, result, actor='system'):
        expected = expected_version(expected)
        text_field(actor, 'actor_name', 80)
        if not isinstance(result, dict):
            raise StoreError('validated_output_required')
        output = result.get('output')
        text_meta = ('trace_id', 'provider', 'prompt_version')
        latency = result.get('latency_ms')
        if (
            result.get('ok') is not True
            or result.get('ai_failed') is not False
            or not isinstance(output, dict)
            or not output
            or any(not isinstance(result.get(k), str) or not result[k].strip() for k in text_meta)
            or result.get('schema_version') != 'event-v0.3'
            or isinstance(latency, bool)
            or not isinstance(latency, (int, float))
            or not math.isfinite(latency)
            or latency < 0
            or not isinstance(result.get('safety_guard_applied'), bool)
        ):
            raise StoreError('validated_output_required')
        with self.transaction() as c:
            event = self._versioned(c, rid, expected)
            if event['state'] not in {'inbox', 'needs_review', 'draft'}:
                raise Conflict('organize_state_invalid')
            related = [self._get(c, related_id) for related_id in event.get('related_record_ids', [])]
            try:
                try:
                    from .adapter import AdapterError, validate_output
                except ImportError:
                    from adapter import AdapterError, validate_output
                validate_output(output, event['raw_text'], {**event, 'history': related})
                draft_json = json.dumps(output, ensure_ascii=False, allow_nan=False)
                meta = {k: result.get(k) for k in (
                    'trace_id', 'provider', 'prompt_version', 'schema_version',
                    'latency_ms', 'safety_guard_applied',
                )}
                meta_json = json.dumps(meta, ensure_ascii=False, allow_nan=False)
            except (AdapterError, TypeError, ValueError) as exc:
                raise StoreError('validated_output_required') from exc
            c.execute('''UPDATE events SET state='draft',version=version+1,
                draft_json=?,result_meta_json=?,updated_at=?
                WHERE record_id=? AND version=?''', (draft_json, meta_json, now(), rid, expected))
            event = self._get(c, rid)
            self.rev(c, event, 'organized', actor)
            self.aud(c, rid, 'organized', event['version'], actor, {'provider': meta.get('provider')})
            return event

    def fail(self, rid, expected, action, actor, details):
        expected = expected_version(expected)
        text_field(actor, 'actor_name', 80)
        with self.transaction() as c:
            event = self._versioned(c, rid, expected)
            self.aud(c, rid, action, event['version'], actor, details)

    def review(self, rid, expected, action, actor, note):
        expected = expected_version(expected)
        text_field(actor, 'actor_name', 80)
        if action not in {'confirm', 'return'}:
            raise StoreError('invalid_review_action')
        if note is not None:
            text_field(note, 'note', 2000, required=False)
        if action == 'return' and (not isinstance(note, str) or not note.strip()):
            raise StoreError('return_note_required')
        with self.transaction() as c:
            event = self._versioned(c, rid, expected)
            if action == 'confirm':
                if event['state'] != 'draft':
                    raise Conflict('confirm_state_invalid')
                if not event['draft']:
                    raise Conflict('draft_required')
                state = 'recorded'
            else:
                if event['state'] not in {'draft', 'recorded'}:
                    raise Conflict('return_state_invalid')
                state = 'needs_review'
            # Draft safety and review fields are intentionally unchanged.
            c.execute('''UPDATE events SET state=?,version=version+1,
                review_notes=?,updated_at=? WHERE record_id=? AND version=?''',
                (state, note or '', now(), rid, expected))
            event = self._get(c, rid)
            self.rev(c, event, 'review_' + action, actor)
            self.aud(c, rid, 'review_' + action, event['version'], actor, {
                'confirmation_scope': 'record_accuracy', 'note': note or '',
            })
            return event

    def revise(self, rid, expected, payload, actor):
        expected = expected_version(expected)
        related = self._payload(payload)
        reason = text_field(payload.get('reason'), 'revision_reason', 2000)
        text_field(actor, 'actor_name', 80)
        with self.transaction() as c:
            old = self._versioned(c, rid, expected)
            if old['state'] == 'superseded':
                raise Conflict('already_superseded')
            for r in related:
                rr = c.execute('SELECT household_id FROM events WHERE record_id=?', (r,)).fetchone()
                if rr is None: raise NotFound('related_record_not_found')
                if rr['household_id'] not in (None, old.get('household_id')): raise Forbidden('cross_household_reference_denied')
            # The old evidence is never edited. Its state/version and a newly
            # appended snapshot record which replacement superseded it.
            new = self._insert(c, payload, related, supersedes_id=rid, reason=reason)
            c.execute('''UPDATE events SET state='superseded',version=version+1,
                updated_at=? WHERE record_id=? AND version=?''', (now(), rid, expected))
            old = self._get(c, rid)
            self.rev(c, old, 'superseded_by_revision', actor)
            self.aud(c, rid, 'superseded_by_revision', old['version'], actor, {
                'new_record_id': new['record_id'], 'reason': reason,
            })
            c.execute('UPDATE events SET household_id=? WHERE record_id=?', (old.get('household_id'), new['record_id']))
            new = self._get(c, new['record_id'])
            self.rev(c, new, 'revised_from', actor)
            self.aud(c, new['record_id'], 'revised_from', new['version'], actor, {
                'supersedes_id': rid, 'superseded_version': expected, 'reason': reason,
            })
            return new

    @staticmethod
    def unresolved_reasons(event):
        reasons = []
        if event.get('local_safety', {}).get('danger_detected'):
            reasons.append('local_danger_detected')
        if event['state'] != 'recorded':
            reasons.append('record_not_confirmed')
        draft = event.get('draft') or {}
        if not draft:
            reasons.append('draft_missing')
        if draft.get('event_kind') in {'medication', 'instruction'}:
            reasons.append('professional_review_required')
        elif draft.get('review_role') in {'clinician_or_pharmacist', 'emergency_services'}:
            reasons.append('professional_review_required')
        if draft.get('escalation_level', 'none') != 'none':
            reasons.append('escalation_not_cleared')
        if draft.get('conflict', {}).get('present'):
            reasons.append('conflict_not_resolved')
        return reasons

    def handoff(self, household_id=None):
        with self.transaction() as c:
            # Superseded evidence stays in history but is not counted twice.
            if household_id:
                rows = c.execute('''SELECT * FROM events
                    WHERE household_id=? AND state IN ('recorded','draft','needs_review','inbox')
                    ORDER BY recorded_at,created_at,record_id''', (household_id,))
            else:
                rows = c.execute('''SELECT * FROM events
                    WHERE state IN ('recorded','draft','needs_review','inbox')
                    ORDER BY recorded_at,created_at,record_id''')
            events = [self.dec(r) for r in rows]
            for event in events:
                event['unresolved_reasons'] = self.unresolved_reasons(event)
                event['unresolved'] = bool(event['unresolved_reasons'])
            handoff = {
                'handoff_id': uid('handoff_'), 'created_at': now(), 'household_id': household_id, 'items': events,
                'unresolved_count': sum(event['unresolved'] for event in events),
            }
            c.execute('INSERT INTO handoffs(handoff_id,created_at,snapshot_json,household_id) VALUES(?,?,?,?)', (
                handoff['handoff_id'], handoff['created_at'],
                json.dumps(handoff, ensure_ascii=False), household_id,
            ))
            return handoff

    def get_handoff(self, hid):
        with self.connection() as c:
            row = c.execute('SELECT snapshot_json FROM handoffs WHERE handoff_id=?', (hid,)).fetchone()
            if row is None:
                raise NotFound('handoff_not_found')
            return json.loads(row['snapshot_json'])
