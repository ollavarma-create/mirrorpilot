#!/usr/bin/env python3
"""Sandbox-only pre-identified replacement and restart recovery experiment.

No privileges or /etc writes. The pre-created replacement inode is journaled
before os.replace. This is a diagnostic prototype, NOT race-free production code.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

BEFORE = b'[fedora]\nbaseurl=https://old.example.org/\n'
AFTER = b'[fedora]\nbaseurl=https://new.example.org/\n'


def identity(path):
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
        raise RuntimeError('unsafe target')
    return (s.st_dev, s.st_ino, stat.S_IMODE(s.st_mode), hashlib.sha256(path.read_bytes()).hexdigest())


def sync_dir(root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def setup(root):
    target, staged, journal = (root / x for x in ('target.repo', 'prepared.repo', 'journal.json'))
    target.write_bytes(BEFORE)
    target.chmod(0o640)
    staged.write_bytes(AFTER)
    staged.chmod(0o640)
    before, after = identity(target), identity(staged)
    with staged.open('rb') as stream:
        os.fsync(stream.fileno())
    journal.write_text(json.dumps({'before': before, 'after': after, 'backup_hex': BEFORE.hex()}))
    with journal.open('rb') as stream:
        os.fsync(stream.fileno())
    sync_dir(root)
    return target, staged, journal


def recover(root):
    target, staged, journal = (root / x for x in ('target.repo', 'prepared.repo', 'journal.json'))
    record = json.loads(journal.read_text())
    before, after = tuple(record['before']), tuple(record['after'])
    now = identity(target)
    if now == before:
        result = 'unchanged'
    elif now == after:
        # Demo only: check-then-replace is subject to TOCTOU.
        restored = root / 'restore.tmp'
        restored.write_bytes(bytes.fromhex(record['backup_hex']))
        restored.chmod(before[2])
        with restored.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(restored, target)
        result = 'restored'
    else:
        return 'conflict'
    journal.unlink()
    if staged.exists():
        staged.unlink()
    sync_dir(root)
    return result


def scenario(label, phase, external=None):
    with tempfile.TemporaryDirectory(prefix='mirrorpilot-identity-') as directory:
        root = Path(directory)
        target, staged, journal = setup(root)
        if phase == 'replaced':
            os.replace(staged, target)
        if external is not None:
            candidate = root / 'external.repo'
            candidate.write_bytes(external)
            candidate.chmod(0o640)
            os.replace(candidate, target)
        previous = identity(target)
        result = recover(root)
        if external is not None:
            ok = result == 'conflict' and identity(target) == previous and journal.exists()
        else:
            ok = result == ('unchanged' if phase == 'prepared' else 'restored') and target.read_bytes() == BEFORE and not journal.exists()
        print(f'{label}: recovery={result}, {"PASS" if ok else "FAIL"}')
        return ok


def main():
    if os.geteuid() == 0:
        print('REFUSED: no root/sudo')
        return 2
    cases = [
        ('PREPARED', 'prepared', None),
        ('REPLACED', 'replaced', None),
        ('PREPARED_ABA', 'prepared', BEFORE),
        ('REPLACED_ABA', 'replaced', AFTER),
        ('REPLACED_EXTERNAL_EDIT', 'replaced', b'external edit'),
    ]
    results = [scenario(*case) for case in cases]
    print(('PASS' if all(results) else 'FAIL') + ': identity-aware sandbox scenarios')
    print('LIMIT: no simultaneous race, inode reuse, SELinux/ACL, or real power failure.')
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
