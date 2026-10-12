"""Encrypted text log. Only text is stored; frames never reach this module."""

from __future__ import annotations

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet


def load_or_create_key(key_path: str) -> bytes:
    p = Path(os.path.expanduser(key_path))
    if p.exists():
        return p.read_bytes().strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    p.write_bytes(key)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return key


class EncryptedLog:
    """Append-only log, one Fernet-encrypted JSON entry per line."""

    def __init__(self, path: str, key: bytes):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = Fernet(key)

    def clear(self) -> None:
        self.path.write_text("")

    def append(self, entry: dict) -> None:
        token = self._f.encrypt(json.dumps(entry, ensure_ascii=False).encode("utf-8"))
        with self.path.open("ab") as fh:
            fh.write(token + b"\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_bytes().splitlines():
            if line.strip():
                out.append(json.loads(self._f.decrypt(line)))
        return out
