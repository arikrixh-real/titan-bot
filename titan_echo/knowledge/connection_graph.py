"""Build best-effort TITAN static connection graph."""

from __future__ import annotations

from typing import Any

from titan_echo.knowledge.common import ast_imports, imported_repo_paths, iter_files, module_for_path, now_utc, output_path, parse_ast, relative, write_json


OUTPUT_PATH = output_path("connection_graph.json")


def build_connection_graph() -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges = []
    for path in iter_files({".py"}):
        rel = relative(path)
        module = module_for_path(rel)
        nodes[rel] = {"id": rel, "module": module, "type": "file"}
        imports = ast_imports(parse_ast(path))
        for target in imported_repo_paths(path, imports):
            edges.append(
                {
                    "from": rel,
                    "to": target,
                    "relationship": "imports_or_depends_on",
                    "evidence": [f"import:{target}"],
                }
            )
    return {
        "schema": "titan_echo.knowledge.connection_graph.v1",
        "generated_at_utc": now_utc(),
        "mode": "best_effort_static_import_graph",
        "summary": {"nodes": len(nodes), "edges": len(edges)},
        "nodes": list(nodes.values()),
        "edges": sorted(edges, key=lambda item: (item["from"], item["to"])),
    }


def write_connection_graph(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    graph = payload or build_connection_graph()
    write_json(OUTPUT_PATH, graph)
    return graph


def main() -> int:
    graph = write_connection_graph()
    print("ECHO connection graph: PASSED")
    print(f"Edges: {graph['summary']['edges']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
