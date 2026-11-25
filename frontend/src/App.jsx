import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Scale, Network, Layers, Database, Sparkles, BarChart3 } from 'lucide-react';
import ChatJudgeView from './components/ChatJudgeView.jsx';
import GraphExplorerView from './components/GraphExplorerView.jsx';
import CardCatalogView from './components/CardCatalogView.jsx';
import DatabaseStatusView from './components/DatabaseStatusView.jsx';
import BenchmarkView from './components/BenchmarkView.jsx';
import CardModal from './components/CardModal.jsx';

const TABS = [
  { id: 'judge', label: 'AI Head Judge', icon: Scale },
  { id: 'graph', label: 'Knowledge Graph', icon: Network },
  { id: 'catalog', label: 'Katalog & Banlist', icon: Layers },
  { id: 'benchmark', label: 'Benchmark & RAGAS', icon: BarChart3 },
  { id: 'status', label: 'Arsitektur', icon: Database },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('judge');
  const [health, setHealth] = useState(null);
  const [modalCard, setModalCard] = useState(null);
  const [graphTarget, setGraphTarget] = useState('Ash Blossom & Joyous Spring');

  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((data) => setHealth(data))
      .catch(() => {});
  }, []);

  const handleInspectInGraph = (entityName) => {
    setGraphTarget(entityName);
    setActiveTab('graph');
  };

  const totalCards = health?.neo4j_stats?.Card || health?.corpus?.cards_total || 14704;
  const totalRels = health?.neo4j_stats?.Relationships || 151125;

  return (
    <div className="app-shell">
      {/* Animated Cyber-Arcane Background */}
      <div className="ambient-bg">
        <div className="ambient-grid" />
        <div className="orb orb-1" />
        <div className="orb orb-2" />
      </div>

      {/* Sticky Glass Navbar */}
      <header className="top-navbar">
        <div className="brand-group">
          <div className="brand-emblem">
            <Sparkles size={20} />
          </div>
          <div>
            <div className="brand-title">YU-GI-OH! GRAPHRAG</div>
            <div className="brand-sub">Hybrid Neo4j Knowledge Graph & AI Head Judge</div>
          </div>
        </div>

        <nav className="nav-tabs">
          {TABS.map((t) => {
            const Icon = t.icon;
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                className={`nav-tab-btn ${isActive ? 'active' : ''}`}
                onClick={() => setActiveTab(t.id)}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeNavPill"
                    className="nav-tab-pill"
                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                  />
                )}
                <Icon size={15} />
                <span>{t.label}</span>
              </button>
            );
          })}
        </nav>

        <div className={`status-pill ${health?.neo4j_connected === false ? 'offline' : ''}`}>
          <span className="pulse-dot" />
          <span>
            {health?.neo4j_connected === false
              ? 'Local Graph Mode'
              : `Neo4j Live · ${totalCards.toLocaleString()} Kartu · ${totalRels.toLocaleString()} Relasi`}
          </span>
        </div>
      </header>

      {/* Animated Page Container */}
      <main className="main-content">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
          >
            {activeTab === 'judge' && <ChatJudgeView onSelectCard={setModalCard} />}
            {activeTab === 'graph' && (
              <GraphExplorerView initialQuery={graphTarget} onSelectCard={setModalCard} />
            )}
            {activeTab === 'catalog' && (
              <CardCatalogView
                onOpenModal={setModalCard}
                onInspectInGraph={handleInspectInGraph}
              />
            )}
            {activeTab === 'benchmark' && <BenchmarkView />}
            {activeTab === 'status' && <DatabaseStatusView health={health} />}
          </motion.div>
        </AnimatePresence>
      </main>

      {/* Global 3D Holographic Card & PSCT Modal */}
      <CardModal
        card={modalCard}
        onClose={() => setModalCard(null)}
        onInspectInGraph={handleInspectInGraph}
      />
    </div>
  );
}
