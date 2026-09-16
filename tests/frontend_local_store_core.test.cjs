const test = require('node:test');
const assert = require('node:assert/strict');

const {
  EncryptedVault,
  MemoryDocumentStore,
} = require('../frontend/local-store-core.js');

test('vault encrypts health text at rest and requires unlock after lock', async () => {
  const driver = new MemoryDocumentStore();
  const vault = new EncryptedVault(driver);
  await vault.setup('a long local recovery passphrase');
  await vault.put('event:one', { raw_text: '胸口疼，需要记下来' });

  const stored = driver.docs.get('event:one');
  assert.equal(JSON.stringify(stored).includes('胸口疼'), false);
  assert.deepEqual(await vault.get('event:one'), { raw_text: '胸口疼，需要记下来' });

  vault.lock();
  await assert.rejects(vault.get('event:one'), /vault_locked/);
  await assert.rejects(vault.unlock('the wrong passphrase'), /decrypt_failed/);
  await vault.unlock('a long local recovery passphrase');
  assert.equal((await vault.get('event:one')).raw_text, '胸口疼，需要记下来');
});

test('encrypted backup previews before restore and rejects corruption', async () => {
  const original = new EncryptedVault(new MemoryDocumentStore());
  await original.setup('a different recovery passphrase');
  await original.put('event:one', { raw_text: '原话一' });
  await original.putBinary('media:one', new Uint8Array([1, 2, 3]).buffer, { contentType: 'image/png' });

  const archive = await original.exportArchive();
  const destination = new EncryptedVault(new MemoryDocumentStore());
  const preview = await destination.previewArchive(archive, 'a different recovery passphrase');
  assert.deepEqual(
    { eventCount: preview.eventCount, mediaCount: preview.mediaCount },
    { eventCount: 1, mediaCount: 1 },
  );
  assert.equal((await destination.status()).configured, false);

  await destination.restoreArchive(archive, 'a different recovery passphrase');
  assert.equal((await destination.get('event:one')).raw_text, '原话一');
  assert.deepEqual([...new Uint8Array((await destination.get('media:one')).bytes)], [1, 2, 3]);

  const corrupt = structuredClone(archive);
  corrupt.docs[0].encrypted.cipher.__health_bytes__ = 'AAAA';
  await assert.rejects(destination.previewArchive(corrupt, 'a different recovery passphrase'), /decrypt_failed/);
});
