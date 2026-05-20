import hashlib
import json


def stable_hash(payload):
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8", errors="replace")
    return hashlib.sha256(encoded).hexdigest()


def hash_text(text):
    return hashlib.sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest()

