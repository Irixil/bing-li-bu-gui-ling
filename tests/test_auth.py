import sqlite3
import tempfile
import unittest

from backend.store import SQLiteStore, Forbidden, Unauthorized


class AuthTests(unittest.TestCase):
 def test_household_members_sessions_and_permissions(self):
    store = SQLiteStore(tempfile.mktemp(suffix='.sqlite3'))
    owner = store.create_household('甲家庭', '甲', 'owner')
    session = store.login(user_id=owner['user_id'], household_id=owner['household_id'])
    assert store.authenticate(session['token'])['role'] == 'owner'
    member = store.add_member(owner['household_id'], '乙', 'elder')
    elder = store.login(user_id=member['user_id'], household_id=owner['household_id'])
    assert len(store.list_members(owner['household_id'])) == 2
    with self.assertRaises(Forbidden):
        store.authorize(elder['token'], 'manage_members')
    assert store.authorize(elder['token'], 'read')['role'] == 'elder'
    store.revoke_session(elder['token'])
    with self.assertRaises(Unauthorized):
        store.authenticate(elder['token'])


 def test_households_are_isolated(self):
    store = SQLiteStore(tempfile.mktemp(suffix='.sqlite3'))
    a = store.create_household('甲', '甲')
    b = store.create_household('乙', '乙')
    sa = store.login(user_id=a['user_id'], household_id=a['household_id'])
    with self.assertRaises(Forbidden):
        store.authorize(sa['token'], 'read', b['household_id'])

 def test_password_is_hashed_and_required_for_credential_accounts(self):
    store = SQLiteStore(tempfile.mktemp(suffix='.sqlite3'))
    owner = store.create_household('凭证家庭', '管理员', password='correct horse battery')
    with sqlite3.connect(store.path) as c:
        row = c.execute('SELECT password_hash,password_salt,password_algorithm,password_iterations FROM users WHERE user_id=?', (owner['user_id'],)).fetchone()
    assert row[0] and row[1] and row[2] == 'pbkdf2_sha256' and row[3] >= 310000
    assert 'correct horse battery' not in repr(row)
    with self.assertRaises(Unauthorized):
        store.login(user_id=owner['user_id'], password='wrong password')
    session = store.login(user_id=owner['user_id'], password='correct horse battery')
    assert store.authenticate(session['token'])['user_id'] == owner['user_id']

 def test_failed_logins_lock_and_success_resets_counter(self):
    store = SQLiteStore(tempfile.mktemp(suffix='.sqlite3'))
    owner = store.create_household('锁定家庭', '管理员', password='a secure password')
    for _ in range(store.MAX_LOGIN_FAILURES):
        with self.assertRaises(Unauthorized):
            store.login(user_id=owner['user_id'], password='bad password')
    with self.assertRaises(Unauthorized) as locked:
        store.login(user_id=owner['user_id'], password='a secure password')
    assert str(locked.exception) == 'account_locked'

 def test_ttl_is_validated_and_revoke_remains_effective(self):
    store = SQLiteStore(tempfile.mktemp(suffix='.sqlite3'))
    owner = store.create_household('会话家庭', '管理员', password='a secure password')
    with self.assertRaises(Exception):
        store.login(user_id=owner['user_id'], password='a secure password', ttl_seconds=0)
    session = store.login(user_id=owner['user_id'], password='a secure password', ttl_seconds=60)
    store.revoke_session(session['token'])
    with self.assertRaises(Unauthorized):
        store.authenticate(session['token'])

if __name__ == '__main__': unittest.main()
