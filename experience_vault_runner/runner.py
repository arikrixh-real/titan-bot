import time

from .chunker import chunk_text
from .deduplicator import merge_lessons
from .file_scanner import scan_source_files
from .memory import (
    load_imported_memory,
    load_processed_index,
    save_imported_memory,
    save_processed_index,
    write_derived_memories,
)
from .packet import build_external_experience_packet
from .report import build_report
from .text_extractor import extract_text
from .vault_paths import PACKET_PATH, REPORT_PATH, ensure_vault_dirs
from .io_utils import atomic_write_json


def run_experience_vault_runner(state=None, state_path=None, intelligence_state=None):
    ensure_vault_dirs()
    index = load_processed_index()
    files_index = index.setdefault("files", {})
    chunks_index = index.setdefault("chunks", {})
    memory = load_imported_memory()
    warnings = []
    new_lessons = []
    stats = {
        "scanned_files": 0,
        "changed_files": 0,
        "skipped_unchanged_files": 0,
        "processed_chunks": 0,
        "skipped_unchanged_chunks": 0,
        "new_lessons": 0,
        "source_type": "EXTERNAL_EXPERIENCE",
    }

    for file_info in scan_source_files():
        stats["scanned_files"] += 1
        source_path = file_info["relative_path"]
        previous = files_index.get(source_path, {})
        if previous.get("file_hash") == file_info["file_hash"]:
            stats["skipped_unchanged_files"] += 1
            continue

        stats["changed_files"] += 1
        text, status, error = extract_text(file_info["path"])
        if status != "ok" or len(text.strip()) < 40:
            warnings.append(
                {
                    "source_file": source_path,
                    "status": status,
                    "reason": error or "too little extractable text",
                }
            )
            files_index[source_path] = {
                **file_info,
                "path": source_path,
                "last_status": "insufficient_extraction",
                "last_processed_at": time.time(),
                "source_type": "EXTERNAL_EXPERIENCE",
            }
            continue

        chunks = chunk_text(text, source_path)
        for chunk in chunks:
            previous_chunk = chunks_index.get(chunk["text_hash"])
            if previous_chunk and previous_chunk.get("source_file") == source_path:
                stats["skipped_unchanged_chunks"] += 1
                continue
            lessons = extract_lessons(chunk, file_info["category"])
            chunks_index[chunk["text_hash"]] = {
                "source_file": source_path,
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "chunk_hash": chunk["text_hash"],
                "processed_at": time.time(),
                "lesson_count": len(lessons),
                "source_type": "EXTERNAL_EXPERIENCE",
            }
            stats["processed_chunks"] += 1
            new_lessons.extend(lessons)

        files_index[source_path] = {
            **file_info,
            "path": source_path,
            "last_status": "ok",
            "chunk_count": len(chunks),
            "last_processed_at": time.time(),
            "source_type": "EXTERNAL_EXPERIENCE",
        }

    memory, merge_stats = merge_lessons(memory, new_lessons)
    stats["new_lessons"] = len(new_lessons)
    stats["memory_added"] = merge_stats["added"]
    stats["memory_updated"] = merge_stats["updated"]
    stats["contradictions"] = merge_stats["contradictions"]
    stats["memory_total"] = merge_stats["total"]

    index["last_run"] = time.time()
    index["last_stats"] = stats
    index["source_type"] = "EXTERNAL_EXPERIENCE"
    save_processed_index(index)
    save_imported_memory(memory)
    write_derived_memories(memory)

    packet = build_external_experience_packet(memory, stats, warnings)
    atomic_write_json(PACKET_PATH, packet)
    REPORT_PATH.write_text(build_report(packet), encoding="utf-8")

    return {
        "status": "ok",
        "runner": "experience_vault_runner",
        "stats": stats,
        "warnings": len(warnings),
        "packet_path": str(PACKET_PATH),
        "report_path": str(REPORT_PATH),
    }


if __name__ == "__main__":
    print(run_experience_vault_runner())

