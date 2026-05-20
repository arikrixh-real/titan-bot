import re

from .hashing import hash_text


def normalize_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def chunk_text(text, source_path, max_chars=3500, overlap=350):
    text = normalize_text(text)
    if not text:
        return []
    chunks = []
    start = 0
    chunk_index = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            sentence_end = max(text.rfind(".", start, end), text.rfind("\n", start, end))
            if sentence_end > start + 1000:
                end = sentence_end + 1
        body = text[start:end].strip()
        if body:
            text_hash = hash_text(body)
            chunks.append(
                {
                    "chunk_id": hash_text(f"{source_path}:{chunk_index}:{text_hash}")[:24],
                    "chunk_index": chunk_index,
                    "source_path": source_path,
                    "text": body,
                    "text_hash": text_hash,
                    "char_count": len(body),
                }
            )
            chunk_index += 1
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks

