"""Lazy TensorFlow model loader with artifact digest verification."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from app.ai.common import AIModelError


def file_hash(path: Path)->str:
    h=sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def load_model(path: Path, expected_hash: str|None=None):
    if not path.is_file(): raise AIModelError(f"TensorFlow model not found: {path}")
    if expected_hash and file_hash(path)!=expected_hash: raise AIModelError("TensorFlow model integrity verification failed")
    try: import tensorflow as tf
    except ImportError as exc: raise AIModelError("TensorFlow is not installed") from exc
    return tf.keras.models.load_model(path,compile=False)
