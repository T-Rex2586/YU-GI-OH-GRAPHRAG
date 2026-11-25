import React from 'react';
import { motion } from 'framer-motion';
import { Database, BookOpen, Layers, Scale, ShieldAlert, Cpu, CheckCircle2 } from 'lucide-react';

export default function DatabaseStatusView({ health }) {
  const stats = health?.neo4j_stats || {};
  const corpus = health?.corpus || {};
  const models = health?.models || {};

  const kpis = [
    {
      label: 'Total Kartu Teranalisis PSCT',
      value: (stats.Card || corpus.cards_total || 0).toLocaleString(),
      sub: 'YGOPRODeck API v7 + PSCT Parser',
      color: '#818cf8',
      icon: Layers,
    },
    {
      label: 'Relasi Knowledge Graph',
      value: (stats.Relationships || 0).toLocaleString(),
      sub: 'Multi-hop Neo4j 5 Relationships',
      color: '#fbbf24',
      icon: Database,
    },
    {
      label: 'Node Ber-vektor Semantik',
      value: (stats.EmbeddedNodes || 0).toLocaleString(),
      sub: `Vector Index (${models.embedding_provider || 'fastembed'})`,
      color: '#34d399',
      icon: Cpu,
    },
    {
      label: 'Rulebook, PSCT & Rulings',
      value: (
        (corpus.rulebook_chunks || 0) +
        (corpus.psct_rules || 0) +
        (corpus.rulings_total || 0)
      ).toLocaleString(),
      sub: `${corpus.banlist_entries || 0} Entri Banlist TCG/OCG/Goat`,
      color: '#38bdf8',
      icon: BookOpen,
    },
  ];

  const schemaBlocks = [
    {
      title: '1. Official Rulebook v10 + Master Rule',
      nodes: '(:RuleSection) -> (:RuleChunk) -> (:GameConcept)',
      desc: 'Menghubungkan aturan fase duel, Chain, Spell Speed 1/2/3, Damage Step, dan zona Extra Deck terbaru langsung ke mekanik kartu.',
      accent: '#fb923c',
    },
    {
      title: '2. Database 14.704 Kartu & Archetype',
      nodes: '(:Card) -> (:Archetype | :Attribute | :MonsterRace)',
      desc: 'Menyimpan properti lengkap seluruh kartu resmi beserta relasi referensi eksplisit (:Card)-[:MENTIONS_CARD]->(:Card).',
      accent: '#818cf8',
    },
    {
      title: '3. Tata Bahasa PSCT & Official Rulings',
      nodes: '(:Ruling)-[:RULES_ON]->(:Card)-[:HAS_PSCT_PATTERN]->(:PSCTRule)',
      desc: 'Memetakan klausa titik dua (:), titik koma (;), Targeting vs Non-Targeting, konjungsi (then / also / and if you do), serta Q&A Konami.',
      accent: '#c084fc',
    },
    {
      title: '4. Daftar Kartu Banned (Forbidden & Limited)',
      nodes: '(:Card)-[:BANNED_IN {status, max_copies}]->(:Format)',
      desc: 'Melacak status Forbidden (0), Limited (1), dan Semi-Limited (2) di format kompetitif TCG, OCG, dan Goat.',
      accent: '#f87171',
    },
  ];

  return (
    <div style={{ display: 'grid', gap: '1.25rem' }}>
      <div className="glass-panel" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.3rem', fontWeight: 700 }}>Arsitektur & Statistik Knowledge Graph</h1>
          <p style={{ fontSize: '0.83rem', color: '#94a3b8', marginTop: '0.2rem' }}>
            Status koneksi langsung ke database graf Neo4j 5, indeks vektor semantik, dan keempat korpus dokumen resmi Yu-Gi-Oh!.
          </p>
        </div>
        <div className={`status-pill ${health?.neo4j_connected ? '' : 'offline'}`}>
          <CheckCircle2 size={15} />
          <span>
            {health?.neo4j_connected
              ? `Neo4j Bolt Aktif · LLM: ${models.llm || 'gemini-2.5-flash'}`
              : 'Mode Fallback Lokal Aktif'}
          </span>
        </div>
      </div>

      <div className="kpi-grid">
        {kpis.map((item, idx) => {
          const Icon = item.icon;
          return (
            <motion.div
              key={item.label}
              className="glass-panel"
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.06 }}
              style={{ borderTop: `3px solid ${item.color}` }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{item.label}</span>
                <Icon size={18} color={item.color} />
              </div>
              <div style={{ fontSize: '1.95rem', fontWeight: 700, color: '#fff', margin: '0.35rem 0 0.2rem' }}>
                {item.value}
              </div>
              <div style={{ fontSize: '0.75rem', color: '#64748b' }}>{item.sub}</div>
            </motion.div>
          );
        })}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: '1rem',
        }}
      >
        {schemaBlocks.map((b, i) => (
          <motion.div
            key={b.title}
            className="glass-panel"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.15 + i * 0.06 }}
            style={{ borderLeft: `3px solid ${b.accent}`, display: 'grid', gap: '0.5rem' }}
          >
            <h3 style={{ fontSize: '0.98rem', fontWeight: 700, color: '#fff' }}>{b.title}</h3>
            <code
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '0.75rem',
                color: b.accent,
                background: 'rgba(6, 10, 20, 0.75)',
                padding: '0.35rem 0.6rem',
                borderRadius: '6px',
              }}
            >
              {b.nodes}
            </code>
            <p style={{ fontSize: '0.82rem', color: '#94a3b8', lineHeight: 1.55 }}>{b.desc}</p>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
