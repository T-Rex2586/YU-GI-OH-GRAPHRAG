"""CLI untuk menjalankan seluruh 7 Skenario Eksperimen & Evaluasi RAGAS Proyek Big Data Storage."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.benchmark_suite import run_all_benchmarks

if __name__ == "__main__":
    results = run_all_benchmarks()
    print("\n================ RINGKASAN HASIL 7 EKSPERIMEN GRAPHRAG ================")
    print("1. Vector vs Graph vs Hybrid:")
    for r in results["exp1_vector_vs_graph_vs_hybrid"]:
        print("  ", r)
    print("\n2. Single-hop vs Multi-hop:")
    for r in results["exp2_single_vs_multihop"]:
        print("  ", r)
    print("\n3. Graph Traversal Latency:")
    for r in results["exp3_graph_traversal_latency"]:
        print("  ", r)
    print("\n4. End-to-End Integration Latency:")
    for r in results["exp4_e2e_integration_latency"]:
        print("  ", r)
    print("\n5. Pertumbuhan Node & Edge:")
    for r in results["exp5_node_edge_growth"]:
        print("  ", r)
    print("\n6. Entity/Relationship Extraction:")
    for r in results["exp6_entity_relationship_extraction"]["summary"]:
        print("  ", r)
    print("\n7. Evaluasi Generatif RAGAS:")
    print("  ", json.dumps(results["exp7_ragas_evaluation"]["aggregate"], indent=2))
