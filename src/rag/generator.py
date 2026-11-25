"""Generator jawaban Hakim Resmi (Head Judge AI) menggunakan Google Gemini API."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import types

from src.config import Settings, get_settings
from src.rag.retriever import RetrievalResult

SYSTEM_PROMPT_JUDGE = """Anda adalah **Yu-Gi-Oh! Official Head Judge & GraphRAG Assistant**.
Tugas Anda adalah menjawab pertanyaan pemain secara akurat, terstruktur, dan mudah dipahami berdasarkan KONTEKS KNOWLEDGE GRAPH yang diberikan dari 4 sumber resmi:
1. Official Rulebook v10 & Revisi Master Rule Terbaru (2020/2021 Rules Update)
2. Database Informasi Kartu (~14.000+ kartu resmi)
3. Aturan PSCT (Problem-Solving Card Text) & Official Konami Card Rulings/FAQ (`db.ygoresources.com`)
4. Daftar Kartu Forbidden & Limited (Banlist TCG, OCG, dan Goat)

ATURAN PENJAWABAN WAJIB:
1. Jawab menggunakan bahasa yang sama dengan pertanyaan pengguna (jika Bahasa Indonesia, jawab dalam Bahasa Indonesia yang jelas namun tetap pertahankan istilah teknis resmi Yu-Gi-Oh! seperti *Chain Link*, *Cost*, *Target*, *Spell Speed*, *Damage Step*, *Missing the Timing*, *Forbidden/Limited*).
2. Saat membahas interaksi efek kartu atau ruling:
   - Bedah teks kartu menggunakan tata bahasa **PSCT**: perhatikan posisi titik dua (`:` = kondisi aktivasi), titik koma (`;` = tindakan saat aktivasi seperti *Cost* dan *Target*), dan teks setelah `;` (efek saat resolusi).
   - Jelaskan konjungsi PSCT bila relevan (`then`, `and if you do`, `also`, `at the same time`) serta apakah terjadi *Missing the Timing* (`When ... you can` vs `If ... you can`).
3. Saat membahas aturan Extra Deck Summon, selalu utamakan **Master Rule Update 2020/2021** (Fusion, Synchro, Xyz dari Extra Deck kini BISA langsung ke Main Monster Zone ataupun Extra Monster Zone tanpa Link Arrow; hanya Link Monster dan face-up Pendulum Monster di Extra Deck yang wajib ke Extra Monster Zone atau zona yang ditunjuk Link Arrow).
4. Cantumkan sitasi sumber secara eksplisit di dalam penjelasan atau di bagian akhir, misalnya `[Kartu: Ash Blossom & Joyous Spring]`, `[PSCT: Semicolon (;)]`, `[Ruling: qa_xxxx]`, `[Rulebook: ...]`, atau `[Banlist TCG/OCG]`.
5. Jika informasi spesifik tidak ditemukan di dalam konteks yang tersedia, nyatakan secara jujur bagian mana yang tidak ada di konteks tanpa mengarang teks efek kartu palsu.
"""


class GraphRAGGenerator:
    """Menghasilkan jawaban akhir (sinkron maupun streaming) dengan Google Gemini API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY belum diatur pada file `.env`.")
        self.client = genai.Client(
            api_key=self.settings.gemini_api_key,
            http_options=types.HttpOptions(api_version="v1beta"),
        )

    def _build_user_prompt(
        self,
        question: str,
        retrieval: RetrievalResult,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> str:
        history_block = ""
        if chat_history:
            recent = chat_history[-4:]
            lines = [f"{m['role'].upper()}: {m['content'][:400]}" for m in recent]
            history_block = "=== RIWAYAT PERCAKAPAN SEBELUMNYA ===\n" + "\n".join(lines) + "\n\n"

        context_block = retrieval.to_prompt_context()
        return (
            f"{history_block}"
            f"{context_block}\n\n"
            f"=== PERTANYAAN PENGGUNA ===\n{question}\n\n"
            "Berikan putusan/jawaban yang akurat, runtut, dan disertai rujukan sumber dari konteks di atas:"
        )

    def generate(
        self,
        question: str,
        retrieval: RetrievalResult,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Menghasilkan jawaban lengkap sekaligus (cocok untuk Notebook & evaluasi batch)."""
        prompt = self._build_user_prompt(question, retrieval, chat_history)
        resp = self.client.models.generate_content(
            model=self.settings.gemini_llm_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT_JUDGE,
                temperature=0.15,
            ),
        )
        return resp.text or ""

    def stream(
        self,
        question: str,
        retrieval: RetrievalResult,
        chat_history: list[dict[str, Any]] | None = None,
    ) -> Iterator[str]:
        """Menghasilkan stream potongan teks token demi token untuk `st.write_stream`."""
        prompt = self._build_user_prompt(question, retrieval, chat_history)
        response_stream = self.client.models.generate_content_stream(
            model=self.settings.gemini_llm_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT_JUDGE,
                temperature=0.15,
            ),
        )
        for chunk in response_stream:
            if chunk.text:
                yield chunk.text
