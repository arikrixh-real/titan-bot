import time

from .belief_builder import build_beliefs, build_research_ideas
from .chunker import chunk_text
from .deduplicator import merge_items
from .evolution_bridge import build_consciousness_packet
from .file_scanner import scan_source_files
from .knowledge_memory import (
    atomic_write_json,
    load_beliefs,
    load_memory,
    load_processed_index,
    load_research_ideas,
    save_beliefs,
    save_memory,
    save_processed_index,
    save_research_ideas,
)
from .knowledge_report import build_report
from .lesson_extractor import extract_lessons
from .text_extractor import extract_text
from .vault_paths import PACKET_PATH, REPORT_PATH, ensure_vault_dirs


def run_knowledge_vault_runner(state=None, state_path=None, intelligence_state=None):
    ensure_vault_dirs()
    index = load_processed_index()
    files_index = index.setdefault("files", {})
    chunks_index = index.setdefault("chunks", {})
    memory = load_memory()
    warnings = []
    new_findings = []
    stats = {
        "scanned_files": 0,
        "changed_files": 0,
        "skipped_unchanged_files": 0,
        "processed_chunks": 0,
        "skipped_unchanged_chunks": 0,
        "new_findings": 0,
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
        if status != "ok" or len(text.strip()) < 80:
            warnings.append({"source_file": source_path, "status": status, "reason": error or "too little extractable text"})
            files_index[source_path] = {**file_info, "path": source_path, "last_status": "insufficient_extraction", "last_processed_at": time.time()}
            continue

        chunks = chunk_text(text, source_path)
        for chunk in chunks:
            previous_chunk = chunks_index.get(chunk["text_hash"])
            if previous_chunk and previous_chunk.get("source_file") == source_path:
                stats["skipped_unchanged_chunks"] += 1
                continue
            findings = extract_lessons(chunk)
            chunks_index[chunk["text_hash"]] = {
                "source_file": source_path,
                "chunk_id": chunk["chunk_id"],
                "chunk_index": chunk["chunk_index"],
                "processed_at": time.time(),
                "finding_count": len(findings),
            }
            stats["processed_chunks"] += 1
            new_findings.extend(findings)
        files_index[source_path] = {**file_info, "path": source_path, "last_status": "ok", "chunk_count": len(chunks), "last_processed_at": time.time()}

    memory, merge_stats = merge_items(memory, new_findings)
    stats["new_findings"] = len(new_findings)
    stats["memory_added"] = merge_stats["added"]
    stats["memory_updated"] = merge_stats["updated"]
    stats["memory_total"] = merge_stats["total"]

    beliefs, belief_stats = build_beliefs(load_beliefs(), memory)
    research_ideas, research_stats = build_research_ideas(load_research_ideas(), memory)
    stats["beliefs_total"] = len(beliefs)
    stats["research_ideas_total"] = len(research_ideas)
    stats["belief_merge"] = belief_stats
    stats["research_merge"] = research_stats

    index["last_run"] = time.time()
    index["last_stats"] = stats
    save_processed_index(index)
    save_memory(memory)
    save_beliefs(beliefs)
    save_research_ideas(research_ideas)

    packet = build_consciousness_packet(memory, beliefs, research_ideas, stats, warnings)
    atomic_write_json(PACKET_PATH, packet)
    REPORT_PATH.write_text(build_report(packet), encoding="utf-8")

    return {
        "status": "ok",
        "runner": "knowledge_vault_runner",
        "stats": stats,
        "warnings": len(warnings),
        "packet_path": str(PACKET_PATH),
        "report_path": str(REPORT_PATH),
    }


if __name__ == "__main__":
    print(run_knowledge_vault_runner())
