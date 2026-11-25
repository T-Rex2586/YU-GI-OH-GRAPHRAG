import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { BarChart3, Award, Gauge, TrendingUp, CheckCircle2, Sparkles, Layers } from 'lucide-react';

function AnimatedBar({ label, value, max = 1, unit = '', color = '#818cf8' }) {
  const pct = Math.min(100, Math.max(2, (value / max) * 100));
  return (
    <div style={{ display: 'grid', gap: '0.28rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem' }}>
        <span style={{ color: '#cbd5e1' }}>{label}</span>
        <strong style={{ color: '#fff' }}>
          {typeof value === 'number' ? value.toLocaleString() : value}
          {unit}
        </strong>
      </div>
      <div
        style={{
          height: 8,
          background: 'rgba(15, 23, 42, 0.9)',
          borderRadius: 999,
          overflow: 'hidden',
          border: '1px solid rgba(148,163,184,0.12)',
        }}
      >
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.65, ease: 'easeOut' }}
          style={{
            height: '100%',
            background: `linear-gradient(90deg, ${color}, #c084fc)`,
            borderRadius: 999,
          }}
        />
      </div>
    </div>
  );
}

export default function BenchmarkView() {
  const [bench, setBench] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/benchmarks')
      .then((r) => r.json())
      .then((d) => setBench(d))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="glass-panel" style={{ textAlign: 'center', padding: '3rem', color: '#94a3b8' }}>
        Memuat hasil eksperimen & evaluasi RAGAS...
      </div>
    );
  }

  if (!bench?.available) {
    return (
      <div className="glass-panel" style={{ padding: '2rem' }}>
        <h2 style={{ fontSize: '1.2rem', color: '#fff' }}>Benchmark belum dijalankan</h2>
        <p style={{ color: '#94a3b8', marginTop: '0.4rem', fontSize: '0.88rem' }}>
          Jalankan <code>python scripts/run_experiments.py</code> untuk menghasilkan seluruh 7 metrik eksperimen wajib.
        </p>
      </div>
    );
  }

  const ragasAgg = bench.exp7_ragas_evaluation?.aggregate || {};
  const exp1 = bench.exp1_vector_vs_graph_vs_hybrid || [];
  const exp2 = bench.exp2_single_vs_multihop || [];
  const exp3 = bench.exp3_graph_traversal_latency || [];
  const exp4 = bench.exp4_e2e_integration_latency || [];
  const exp5 = bench.exp5_node_edge_growth || [];
  const exp6 = bench.exp6_entity_relationship_extraction?.summary || [];
  const ragasSamples = bench.exp7_ragas_evaluation?.samples || [];

  return (
    <div style={{ display: 'grid', gap: '1.25rem' }}>
      {/* Header & RAGAS Top Highlights */}
      <div
        className="glass-panel"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <h1 style={{ fontSize: '1.32rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
            <BarChart3 size={22} color="#fbbf24" /> Hasil 7 Skenario Eksperimen & Evaluasi RAGAS
          </h1>
          <p style={{ fontSize: '0.82rem', color: '#94a3b8', marginTop: '0.2rem' }}>
            Pengukuran empiris sesuai rubrik Big Data Storage (Topik: Graph RAG) pada Neo4j 5 ({bench.graph_statistics?.Card?.toLocaleString()} Kartu & {bench.graph_statistics?.Relationships?.toLocaleString()} Relasi).
          </p>
        </div>
        <span className="badge badge-unlimited">
          <CheckCircle2 size={13} /> Terverifikasi · {bench.generated_at}
        </span>
      </div>

      {/* RAGAS Score Cards */}
      <div className="kpi-grid">
        <div className="glass-panel" style={{ borderTop: '3px solid #34d399' }}>
          <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>RAGAS Faithfulness</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#fff', margin: '0.25rem 0' }}>
            {((ragasAgg.faithfulness || 0) * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: '0.74rem', color: '#34d399' }}>Konsistensi faktual terhadap konteks Graf</div>
        </div>
        <div className="glass-panel" style={{ borderTop: '3px solid #818cf8' }}>
          <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>RAGAS Response Relevancy</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#fff', margin: '0.25rem 0' }}>
            {((ragasAgg.response_relevancy || 0) * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: '0.74rem', color: '#818cf8' }}>Kemiripan kosinus reverse-question</div>
        </div>
        <div className="glass-panel" style={{ borderTop: '3px solid #fbbf24' }}>
          <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>RAGAS Context Recall</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#fff', margin: '0.25rem 0' }}>
            {((ragasAgg.context_recall || 0) * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: '0.74rem', color: '#fbbf24' }}>Cakupan fakta ground-truth</div>
        </div>
        <div className="glass-panel" style={{ borderTop: '3px solid #38bdf8' }}>
          <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>Hybrid MRR Terbaik</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#fff', margin: '0.25rem 0' }}>
            {exp1[2]?.mrr?.toFixed(3) || '-'}
          </div>
          <div style={{ fontSize: '0.74rem', color: '#38bdf8' }}>Mean Reciprocal Rank (Hybrid GraphRAG)</div>
        </div>
      </div>

      {/* Eksperimen 1 & Eksperimen 6 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.15rem' }}>
        <div className="glass-panel" style={{ display: 'grid', gap: '0.85rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
            1. Vector vs. Graph vs. Hybrid (Recall@K & MRR)
          </h3>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Strategi</th>
                  <th>Recall@3</th>
                  <th>Recall@5</th>
                  <th>MRR</th>
                  <th>Latency</th>
                </tr>
              </thead>
              <tbody>
                {exp1.map((r) => (
                  <tr key={r.strategy}>
                    <td style={{ fontWeight: 600, color: '#fff' }}>{r.strategy}</td>
                    <td>{(r.recall_at_3 * 100).toFixed(1)}%</td>
                    <td>{(r.recall_at_5 * 100).toFixed(1)}%</td>
                    <td style={{ color: '#fbbf24', fontWeight: 700 }}>{r.mrr.toFixed(4)}</td>
                    <td>{r.avg_latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {exp1.map((r) => (
            <AnimatedBar
              key={r.strategy}
              label={`${r.strategy} (Recall@5)`}
              value={Number((r.recall_at_5 * 100).toFixed(1))}
              max={100}
              unit="%"
              color={r.strategy.includes('Hybrid') ? '#34d399' : '#818cf8'}
            />
          ))}
        </div>

        <div className="glass-panel" style={{ display: 'grid', gap: '0.85rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
            2. Single-hop vs. Multi-hop Queries (Answer Accuracy)
          </h3>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Konfigurasi</th>
                  <th>Tipe Kueri</th>
                  <th>Completeness</th>
                  <th>Accuracy</th>
                </tr>
              </thead>
              <tbody>
                {exp2.map((r, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, color: '#e2e8f0' }}>{r.configuration}</td>
                    <td>
                      <span className={`badge ${r.query_complexity === 'multi-hop' ? 'badge-semi' : 'badge-info'}`}>
                        {r.query_complexity}
                      </span>
                    </td>
                    <td>{(r.context_completeness * 100).toFixed(1)}%</td>
                    <td style={{ color: '#34d399', fontWeight: 700 }}>
                      {(r.answer_accuracy * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Eksperimen 3 & 4 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.15rem' }}>
        <div className="glass-panel" style={{ display: 'grid', gap: '0.85rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
            3. Graph Traversal (Query Latency 1-Hop s.d. 3-Hop)
          </h3>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Kedalaman Hop</th>
                  <th>Rata-rata Node</th>
                  <th>Mean (ms)</th>
                  <th>p50 (ms)</th>
                  <th>p95 (ms)</th>
                </tr>
              </thead>
              <tbody>
                {exp3.map((r) => (
                  <tr key={r.traversal_depth}>
                    <td style={{ fontWeight: 600, color: '#fff' }}>{r.traversal_depth}</td>
                    <td>{r.avg_nodes_reached}</td>
                    <td style={{ color: '#38bdf8', fontWeight: 600 }}>{r.mean_latency_ms} ms</td>
                    <td>{r.p50_latency_ms} ms</td>
                    <td style={{ color: '#fbbf24' }}>{r.p95_latency_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="glass-panel" style={{ display: 'grid', gap: '0.85rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
            4. Integrasi Graph + Vector (End-to-End Retrieval Latency)
          </h3>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Mode Pipeline</th>
                  <th>Embed</th>
                  <th>Vector DB</th>
                  <th>Graph DB</th>
                  <th>Total E2E</th>
                </tr>
              </thead>
              <tbody>
                {exp4.map((r) => (
                  <tr key={r.pipeline_mode}>
                    <td style={{ fontWeight: 600, color: '#fff' }}>{r.pipeline_mode}</td>
                    <td>{r.query_embedding_ms} ms</td>
                    <td>{r.neo4j_vector_search_ms} ms</td>
                    <td>{r.neo4j_graph_traversal_ms} ms</td>
                    <td style={{ color: '#34d399', fontWeight: 700 }}>{r.end_to_end_retrieval_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Eksperimen 5 & 6 */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.15rem' }}>
        <div className="glass-panel" style={{ display: 'grid', gap: '0.85rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
            5. Pertumbuhan Jumlah Node & Edge (Latency & Storage Size)
          </h3>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Skala</th>
                  <th>Total Node</th>
                  <th>Total Edge</th>
                  <th>Latency</th>
                  <th>Neo4j Store</th>
                </tr>
              </thead>
              <tbody>
                {exp5.map((r) => (
                  <tr key={r.dataset_scale}>
                    <td style={{ fontWeight: 700, color: '#fbbf24' }}>{r.dataset_scale}</td>
                    <td>{r.total_nodes.toLocaleString()}</td>
                    <td>{r.total_edges.toLocaleString()}</td>
                    <td>{r.avg_query_latency_ms} ms</td>
                    <td style={{ color: '#38bdf8' }}>{r.neo4j_storage_mb} MB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="glass-panel" style={{ display: 'grid', gap: '0.85rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
            6. Entity & Relationship Extraction (Precision, Recall, F1)
          </h3>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Modul Ekstraktor</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>F1-Score</th>
                </tr>
              </thead>
              <tbody>
                {exp6.map((r) => (
                  <tr key={r.extractor_module}>
                    <td style={{ fontWeight: 600, color: '#fff' }}>{r.extractor_module}</td>
                    <td style={{ color: '#34d399' }}>{(r.precision * 100).toFixed(1)}%</td>
                    <td style={{ color: '#38bdf8' }}>{(r.recall * 100).toFixed(1)}%</td>
                    <td style={{ color: '#fbbf24', fontWeight: 700 }}>{(r.f1_score * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Eksperimen 7 Detail RAGAS */}
      <div className="glass-panel" style={{ display: 'grid', gap: '0.85rem' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
          7. Evaluasi Jawaban Generatif LLM (RAGAS Per Domain Dokumen)
        </h3>
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Domain</th>
                <th>Pertanyaan Uji</th>
                <th>Faithfulness</th>
                <th>Response Relevancy</th>
                <th>Context Recall</th>
              </tr>
            </thead>
            <tbody>
              {ragasSamples.map((s) => (
                <tr key={s.id}>
                  <td style={{ fontWeight: 700, color: '#818cf8' }}>{s.id}</td>
                  <td>
                    <span className="badge badge-indigo">{s.domain}</span>
                  </td>
                  <td style={{ maxWidth: 420 }}>{s.question}</td>
                  <td style={{ color: '#34d399', fontWeight: 700 }}>
                    {(s.faithfulness * 100).toFixed(1)}%
                  </td>
                  <td style={{ color: '#38bdf8', fontWeight: 700 }}>
                    {(s.response_relevancy * 100).toFixed(1)}%
                  </td>
                  <td style={{ color: '#fbbf24', fontWeight: 700 }}>
                    {(s.context_recall * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
