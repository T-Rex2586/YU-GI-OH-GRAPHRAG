"""Peluncur satu pintu aplikasi Web React + FastAPI Yu-Gi-Oh! Hybrid GraphRAG.

Jalankan:
    python run_web.py
Lalu buka URL yang ditampilkan (default http://localhost:8080) di browser Anda!
"""

from __future__ import annotations

import socket
import uvicorn


def pick_free_port(candidates: tuple[int, ...] = (8080, 8088, 8787)) -> int:
    for port in candidates:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return 8090


if __name__ == "__main__":
    port = pick_free_port()
    print("\n========================================================")
    print("  Yu-Gi-Oh! Hybrid GraphRAG (React + FastAPI + Neo4j)")
    print(f"  Buka di Browser: http://localhost:{port}")
    print("========================================================\n")
    uvicorn.run("backend.api:app", host="127.0.0.1", port=port, reload=False)
