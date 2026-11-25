"""Batch Embedder mendukung Google Gemini API (gemini-embedding-001) & FastEmbed Lokal (768d)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from loguru import logger

from src.config import EMBED_CACHE_DIR, Settings, get_settings

_FASTEMBED_INSTANCES: dict[str, Any] = {}


def _get_fastembed_model(model_name: str) -> Any:
    if model_name not in _FASTEMBED_INSTANCES:
        import os
        from fastembed import TextEmbedding

        # Batasi intra-op threads ke ~6-8 core agar tidak terjadi spinlock contention pada CPU hybrid P+E Windows
        opt_threads = min(8, max(2, (os.cpu_count() or 4) // 2))
        logger.info(
            f"Memuat model embedding lokal FastEmbed ONNX: {model_name} (threads={opt_threads}) ..."
        )
        _FASTEMBED_INSTANCES[model_name] = TextEmbedding(
            model_name=model_name,
            threads=opt_threads,
        )
    return _FASTEMBED_INSTANCES[model_name]


class GeminiEmbedder:
    """Pengelola vektor embedding (mendukung provider `gemini` maupun `fastembed` 768d) dengan cache."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.provider = (self.settings.embedding_provider or "gemini").lower().strip()
        self.dimension = self.settings.embedding_dimension

        if self.provider == "fastembed":
            self.model = self.settings.fastembed_model
            self.dimension = 768 if "base" in self.model.lower() else 384
            self.client = None
        else:
            if not self.settings.gemini_api_key:
                raise ValueError(
                    "GEMINI_API_KEY belum diatur! Isi di file .env atau gunakan EMBEDDING_PROVIDER=fastembed."
                )
            self.model = self.settings.gemini_embedding_model
            self.dimension = int(self.settings.embedding_dimension or 768)
            self.client = genai.Client(
                api_key=self.settings.gemini_api_key,
                http_options=types.HttpOptions(api_version="v1beta"),
            )

        safe_model_tag = f"{self.provider}_{self.model.replace('/', '_')}_{self.dimension}d"
        # Kompatibilitas mundur dengan nama file cache sebelumnya untuk Gemini
        legacy_file = EMBED_CACHE_DIR / f"cache_{self.model.replace('/', '_')}_{self.dimension}d.jsonl"
        self.cache_file: Path = (
            legacy_file
            if (self.provider == "gemini" and legacy_file.exists())
            else (EMBED_CACHE_DIR / f"cache_{safe_model_tag}.jsonl")
        )
        self._cache: dict[str, list[float]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        if not self.cache_file.exists():
            return
        loaded = 0
        with self.cache_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    self._cache[rec["h"]] = rec["v"]
                    loaded += 1
                except Exception:
                    continue
        if loaded:
            logger.info(f"Memuat {loaded:,} vektor embedding ({self.provider}) dari cache lokal.")

    def _hash_text(self, text: str, task_type: str) -> str:
        raw = f"{self.model}|{self.dimension}|{task_type}|{text}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def embed_query(self, query: str) -> list[float]:
        """Menghasilkan embedding 1 kalimat kueri pencarian pengguna."""
        h = self._hash_text(query, "RETRIEVAL_QUERY")
        if h in self._cache:
            return self._cache[h]

        if self.provider == "fastembed":
            fe = _get_fastembed_model(self.model)
            vec = [float(x) for x in next(iter(fe.query_embed(query)))]
        else:
            assert self.client is not None
            resp = self.client.models.embed_content(
                model=self.model,
                contents=query,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=self.dimension,
                ),
            )
            vec = list(resp.embeddings[0].values)

        self._cache[h] = vec
        return vec

    def embed_documents(
        self,
        items: list[dict[str, Any]],
        id_key: str = "id",
        text_key: str = "embed_text",
        batch_size: int = 25,
        sleep_between_batches: float = 1.2,
    ) -> dict[Any, list[float]]:
        """Menghasilkan embedding dokumen secara batch dengan checkpoint disk & proteksi kuota TPM."""
        results: dict[Any, list[float]] = {}
        pending: list[tuple[Any, str, str]] = []

        for item in items:
            item_id = item[id_key]
            text = (item.get(text_key) or "").strip()
            if not text:
                continue
            if len(text) > 4500:
                text = text[:4500]
            h = self._hash_text(text, "RETRIEVAL_DOCUMENT")
            if h in self._cache:
                results[item_id] = self._cache[h]
            else:
                pending.append((item_id, text, h))

        if not pending:
            return results

        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Jalur cepat lokal menggunakan FastEmbed ONNX (diurutkan berdasarkan panjang teks agar bebas padding berlebih!)
        if self.provider == "fastembed":
            fe = _get_fastembed_model(self.model)
            logger.info(
                f"Menghitung embedding lokal FastEmbed ({self.model}, {self.dimension}d) untuk "
                f"{len(pending):,} item baru ({len(results):,} sudah di cache)..."
            )
            # Urutkan berdasarkan panjang karakter agar micro-batch pendek tidak ter-padding ke 512 token
            pending_sorted = sorted(
                [(item_id, text[:1800], h) for item_id, text, h in pending],
                key=lambda x: len(x[1]),
            )
            fe_chunk = 500
            with self.cache_file.open("a", encoding="utf-8") as cache_out:
                for start in range(0, len(pending_sorted), fe_chunk):
                    batch = pending_sorted[start : start + fe_chunk]
                    texts = [b[1] for b in batch]
                    vecs = list(fe.passage_embed(texts, batch_size=16))
                    for (item_id, _, h), raw_vec in zip(batch, vecs):
                        vec = [float(x) for x in raw_vec]
                        self._cache[h] = vec
                        results[item_id] = vec
                        cache_out.write(json.dumps({"h": h, "v": vec}) + "\n")
                    cache_out.flush()
                    done = min(start + fe_chunk, len(pending_sorted))
                    logger.info(
                        f"Progres FastEmbed: {done:,}/{len(pending_sorted):,} ({done / len(pending_sorted) * 100:.1f}%)"
                    )
            return results

        # Jalur Google Gemini API (aman terhadap plafon 30.000 TPM Free Tier dengan batch_size=25)
        assert self.client is not None
        logger.info(
            f"Menghitung embedding Gemini ({self.model}, {self.dimension}d) untuk {len(pending):,} item baru "
            f"({len(results):,} sudah ada di cache)..."
        )

        with self.cache_file.open("a", encoding="utf-8") as cache_out:
            for start in range(0, len(pending), batch_size):
                batch = pending[start : start + batch_size]
                texts = [b[1] for b in batch]

                attempt = 0
                while True:
                    try:
                        resp = self.client.models.embed_content(
                            model=self.model,
                            contents=texts,
                            config=types.EmbedContentConfig(
                                task_type="RETRIEVAL_DOCUMENT",
                                output_dimensionality=self.dimension,
                            ),
                        )
                        break
                    except Exception as exc:
                        attempt += 1
                        err_msg = str(exc)
                        if "PerDay" in err_msg or "per_day" in err_msg.lower():
                            raise RuntimeError(
                                f"Kuota harian Gemini Embedding Free Tier tercapai ({err_msg}). "
                                "Semua vektor sebelumnya telah aman tersimpan di cache! "
                                "Anda dapat beralih ke EMBEDDING_PROVIDER=fastembed untuk menyelesaikan 14.704 kartu secara lokal."
                            ) from exc
                        if attempt <= 8 and (
                            "429" in err_msg
                            or "RESOURCE_EXHAUSTED" in err_msg
                            or "503" in err_msg
                            or "UNAVAILABLE" in err_msg
                        ):
                            wait_sec = min(62.0, 15.0 * attempt)
                            logger.warning(
                                f"Menyesuaikan rate-limit per menit Gemini API (percobaan {attempt}/8). Menunggu {wait_sec:.0f} detik..."
                            )
                            time.sleep(wait_sec)
                        else:
                            raise

                for (item_id, _, h), emb_obj in zip(batch, resp.embeddings):
                    vec = list(emb_obj.values)
                    self._cache[h] = vec
                    results[item_id] = vec
                    cache_out.write(json.dumps({"h": h, "v": vec}) + "\n")
                cache_out.flush()

                completed_now = min(start + batch_size, len(pending))
                if completed_now % 200 == 0 or completed_now == len(pending):
                    pct = (completed_now / len(pending)) * 100
                    logger.info(
                        f"Progres embedding Gemini: {completed_now:,}/{len(pending):,} ({pct:.1f}%)"
                    )

                if start + batch_size < len(pending) and sleep_between_batches > 0:
                    time.sleep(sleep_between_batches)

        return results
