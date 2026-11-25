# Yu-Gi-Oh! Hybrid GraphRAG (React + FastAPI + Neo4j + Gemini)

Sistem **Hybrid GraphRAG (Graph Retrieval-Augmented Generation)** untuk permainan kartu **Yu-Gi-Oh!** yang memadukan **Vector Search (`all-MiniLM-L6-v2` ONNX / `gemini-embedding-001`)**, **Fulltext BM25 Search**, dan **Multi-Hop Cypher Graph Traversal** di atas **Neo4j 5** dengan antarmuka web modern **React + Vite + Framer Motion** bertema *Master Duel Cyber-Arcane*.

Sistem ini mengintegrasikan 4 sumber dokumen resmi yang saling terhubung di dalam Knowledge Graph:
1. **Official Rulebook v10 + Master Rule Revision (2020/2021 Update)** — aturan dasar permainan, fase giliran, *Chain*, *Spell Speed 1/2/3*, *Damage Step*, serta aturan zona Extra Deck terbaru.
2. **Database Informasi Kartu (~14.704 Kartu)** — atribut, tipe, level/rank/link, ATK/DEF, *archetype*, dan relasi referensi antar-kartu dari **YGOPRODeck API v7**.
3. **Card Rulings & Problem-Solving Card Text (PSCT)** — pembedah otomatis tata bahasa PSCT (`Kondisi : Aktivasi/Cost/Target ; Efek Resolusi`, konjungsi `then`, `and if you do`, `also`, *Missing the Timing*, *HOPT vs SOPT*) serta Q&A Ruling resmi dari **`db.ygoresources.com`**.
4. **Daftar Kartu Dibanned (Forbidden & Limited List)** — status legalitas *Forbidden (0)*, *Limited (1)*, dan *Semi-Limited (2)* lintas format **TCG**, **OCG**, dan **Goat**.

---

## Fitur Utama Antarmuka React
- **3D Holographic Foil Card Tilt:** Efek kemiringan perspektif 3D & kilau pelangi holografik yang mengikuti kursor pada ilustrasi kartu.
- **AI Head Judge (SSE Real-Time Streaming):** Asisten hakim resmi dengan animasi tahapan *Query Router → Multi-Hop Neo4j Retrieval → Gemini Stream*, lengkap dengan strip kartu rujukan interaktif.
- **60fps Interactive Knowledge Graph Canvas:** Simulasi fisika *force-directed* 2D dengan partikel cahaya mengalir di sepanjang garis relasi, *drag & zoom*, sorotan tetangga, dan *double-click* untuk memusatkan sub-graf baru.
- **Katalog Instan 14.704 Kartu, Live PSCT Dissector, & Banlist:** Tabel interaktif + mode galeri 3D foil serta komparasi Banlist TCG / OCG / Goat.

---

## Struktur Projek

```text
YU-GI-OH-GRAPHRAG/
├── .env.example                        # Template konfigurasi Gemini API, FastEmbed, & Neo4j
├── docker-compose.yml                  # Server Neo4j 5 Community + APOC
├── requirements.txt                    # Dependensi Python
├── run_web.py                          # Peluncur satu pintu FastAPI + React SPA
├── backend/
│   └── api.py                          # REST API & SSE Streaming Server (FastAPI)
├── frontend/                           # Aplikasi Web React 19 + Vite + Framer Motion
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── styles.css
│       └── components/
│           ├── HoloCard.jsx            # Komponen kartu 3D Holographic Tilt
│           ├── CardModal.jsx           # Modal inspeksi kartu & warna klausa PSCT
│           ├── ChatJudgeView.jsx       # Halaman chat AI Head Judge (SSE)
│           ├── GraphExplorerView.jsx   # Kanvas jaringan Knowledge Graph 60fps
│           ├── CardCatalogView.jsx     # Katalog 14.704 kartu & analitik Banlist
│           └── DatabaseStatusView.jsx  # Statistik live Neo4j & arsitektur skema
├── scripts/
│   └── run_pipeline.py                 # CLI akuisisi data, ingesti Neo4j, & vektorisasi
├── src/
│   ├── config.py                       # Konfigurasi terpusat
│   ├── ingestion/                      # Akuisisi 4 dokumen & parser tata bahasa PSCT
│   ├── graph/                          # Driver Neo4j, skema indeks, & batch embedder
│   └── rag/                            # Query Router, Hybrid Retriever, & Gemini Judge
├── notebooks/
│   └── yugioh_graphrag_experiment.ipynb # Jupyter Notebook eksperimen & evaluasi bertahap
└── tests/
    └── test_yugioh_graphrag.py         # Pengujian otomatis PSCT, Retriever, & FastAPI
```

---

## Cara Instalasi & Menjalankan

### 1. Konfigurasi Environment
```powershell
pip install -r requirements.txt
Copy-Item .env.example .env
# Isi GEMINI_API_KEY di dalam file .env
```

### 2. Jalankan Neo4j & Bangun Knowledge Graph
```powershell
docker compose up -d
python scripts/run_pipeline.py --all --embedding-provider fastembed --max-card-embeddings 0
```

### 3. Build Frontend React & Jalankan Server Web
```powershell
cd frontend
npm install
npm run build
cd ..
python run_web.py
```
Buka **`http://localhost:8080`** di browser Anda. *(Untuk mode pengembangan frontend dengan hot-reload, jalankan `npm run dev` di dalam folder `frontend/`).*
