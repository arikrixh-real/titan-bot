import hashlib
from pathlib import Path

from .vault_paths import upload_paths


SUPPORTED_SUFFIXES = {".txt", ".md", ".csv", ".json", ".pdf"}


def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_source_files():
    files = []
    for folder in upload_paths():
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            stat = path.stat()
            files.append(
                {
                    "path": path,
                    "relative_path": str(path).replace("\\", "/"),
                    "suffix": path.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                    "file_hash": hash_file(path),
                    "category": path.parent.name,
                }
            )
    return files

