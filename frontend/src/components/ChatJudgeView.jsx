import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Scale,
  Send,
  Sparkles,
  User,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  BookOpen,
  ShieldAlert,
  Cpu,
  Network,
} from 'lucide-react';
import { BanBadge } from './CardModal.jsx';

const SCENARIOS = [
  {
    title: 'Aturan Zona Extra Deck Terbaru',
    subtitle: 'Master Rule 2020/2021 vs Rulebook v10 untuk Fusion, Synchro, Xyz, Pendulum, & Link.',
    badge: 'Rulebook + Master Rule',
    prompt:
      'Bagaimana aturan Summon Fusion, Synchro, Xyz, Pendulum, dan Link Monster dari Extra Deck ke Main Monster Zone menurut Master Rule terbaru?',
  },
  {
    title: 'Interaksi Ash Blossom di Damage Step',
    subtitle: 'Mengapa efek negate aktivasi vs negate efek berbeda legalitasnya saat Damage Step?',
    badge: 'Damage Step + PSCT',
    prompt:
      'Apakah Ash Blossom & Joyous Spring bisa diaktifkan saat Damage Step? Jelaskan alasannya berdasarkan aturan Damage Step dan PSCT!',
  },
  {
    title: 'Non-Targeting Banish Mirrorjade',
    subtitle: 'Bedah posisi titik koma (;) pada efek Mirrorjade terhadap monster kebal target.',
    badge: 'PSCT Semicolon (;)',
    prompt:
      "Mengapa efek Mirrorjade the Iceblade Dragon bisa mem-banish monster lawan yang memiliki proteksi 'cannot be targeted by card effects'? Bedah kalimat PSCT-nya!",
  },
  {
    title: 'Komparasi Banlist TCG vs OCG',
    subtitle: 'Bandingkan status legalitas Maxx "C", Baronne de Fleur, dan Pot of Greed.',
    badge: 'Banlist Format',
    prompt:
      'Apa perbedaan status banlist Maxx "C", Baronne de Fleur, dan Pot of Greed di format TCG dibanding OCG?',
  },
];

function TraceAccordion({ context, plan, totalSec, onSelectCard }) {
  const [open, setOpen] = useState(false);
  if (!context) return null;

  return (
    <div style={{ marginBottom: '0.85rem' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          background: 'rgba(99, 102, 241, 0.12)',
          border: '1px solid rgba(99, 102, 241, 0.3)',
          color: '#c7d2fe',
          padding: '0.38rem 0.78rem',
          borderRadius: '9px',
          fontSize: '0.78rem',
          fontWeight: 500,
          cursor: 'pointer',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '0.45rem',
        }}
      >
        <Network size={14} />
        <span>
          Jejak {context.mode} · {context.cards?.length || 0} Kartu ·{' '}
          {context.graph_paths?.length || 0} Relasi Graf ({totalSec || context.elapsed_sec}s)
        </span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            style={{ overflow: 'hidden' }}
          >
            <div
              style={{
                marginTop: '0.65rem',
                padding: '0.85rem',
                borderRadius: '11px',
                background: 'rgba(6, 10, 20, 0.78)',
                border: '1px solid rgba(148, 163, 184, 0.15)',
                fontSize: '0.8rem',
                display: 'grid',
                gap: '0.5rem',
              }}
            >
              {plan && (
                <div>
                  <strong style={{ color: '#94a3b8' }}>Kueri Teknis (EN):</strong>{' '}
                  <code style={{ color: '#38bdf8' }}>{plan.english_query}</code>
                </div>
              )}
              {context.psct_rules?.length > 0 && (
                <div>
                  <strong style={{ color: '#94a3b8' }}>Aturan PSCT:</strong>{' '}
                  {context.psct_rules.map((p) => p.name).join(' · ')}
                </div>
              )}
              {context.rulings?.length > 0 && (
                <div>
                  <strong style={{ color: '#94a3b8' }}>Official Rulings:</strong>{' '}
                  {context.rulings.map((r) => r.id).join(', ')}
                </div>
              )}
              {context.graph_paths?.length > 0 && (
                <pre
                  style={{
                    background: '#04070f',
                    padding: '0.65rem',
                    borderRadius: '8px',
                    fontSize: '0.74rem',
                    color: '#a5b4fc',
                    overflowX: 'auto',
                  }}
                >
                  {context.graph_paths.slice(0, 8).join('\n')}
                </pre>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {context.cards?.length > 0 && (
        <div className="ref-cards-strip">
          {context.cards.slice(0, 4).map((c) => (
            <div
              key={c.id}
              className="ref-mini-card"
              onClick={() => onSelectCard(c)}
              title="Klik untuk bedah 3D & PSCT"
            >
              {c.image_url && <img src={c.image_url} alt={c.name} />}
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    color: '#f8fafc',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {c.name}
                </div>
                <div style={{ fontSize: '0.7rem', color: '#94a3b8', marginBottom: '0.25rem' }}>
                  {c.type}
                </div>
                <BanBadge format="TCG" status={c.ban_tcg} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatJudgeView({ onSelectCard }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [useLlmRouter, setUseLlmRouter] = useState(true);
  const [strategy, setStrategy] = useState('hybrid');
  const [liveStage, setLiveStage] = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, liveStage]);

  const sendQuestion = async (questionText) => {
    const trimmed = questionText.trim();
    if (!trimmed || streaming) return;

    const priorHistory = messages.map((m) => ({ role: m.role, content: m.content }));
    setInput('');
    setStreaming(true);
    setLiveStage('Menghubungkan ke AI Head Judge...');

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: trimmed },
      { role: 'assistant', content: '', context: null, plan: null, totalSec: null },
    ]);

    try {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: trimmed,
          history: priorHistory,
          use_llm_router: useLlmRouter,
          strategy,
          hop_depth: 2,
        }),
      });

      if (!resp.ok) {
        const errBody = await resp.text();
        throw new Error(errBody || `HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const block of parts) {
          const lines = block.split('\n');
          let eventType = 'message';
          let dataStr = '';
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim();
            if (line.startsWith('data: ')) dataStr += line.slice(6);
          }
          if (!dataStr) continue;
          const payload = JSON.parse(dataStr);

          if (eventType === 'step') {
            setLiveStage(payload.message);
          } else if (eventType === 'plan') {
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { ...next[next.length - 1], plan: payload };
              return next;
            });
          } else if (eventType === 'context') {
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { ...next[next.length - 1], context: payload };
              return next;
            });
          } else if (eventType === 'token') {
            setLiveStage('');
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              next[next.length - 1] = { ...last, content: last.content + payload.text };
              return next;
            });
          } else if (eventType === 'done') {
            setLiveStage('');
            setMessages((prev) => {
              const next = [...prev];
              next[next.length - 1] = { ...next[next.length - 1], totalSec: payload.total_sec };
              return next;
            });
          } else if (eventType === 'error') {
            throw new Error(payload.message);
          }
        }
      }
    } catch (err) {
      setLiveStage('');
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          ...next[next.length - 1],
          content: `**Terjadi kendala:** ${err.message}`,
        };
        return next;
      });
    } finally {
      setStreaming(false);
      setLiveStage('');
    }
  };

  return (
    <div className="chat-layout">
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
          <h1 style={{ fontSize: '1.35rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
            <Scale size={22} color="#fbbf24" /> Yu-Gi-Oh! Official AI Head Judge
          </h1>
          <p style={{ fontSize: '0.84rem', color: '#94a3b8', marginTop: '0.25rem' }}>
            Penelusuran multi-hop di atas <strong>14.704 Kartu</strong>, <strong>Rulebook + Master Rule</strong>,{' '}
            <strong>Tata Bahasa PSCT & Rulings</strong>, serta <strong>Banlist TCG/OCG</strong>.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
          {[
            ['hybrid', 'Hybrid (Graph+Vector)'],
            ['vector', 'Vector-Only'],
            ['graph', 'Graph-Only'],
          ].map(([val, label]) => (
            <button
              key={val}
              className={`chip-btn ${strategy === val ? 'active' : ''}`}
              onClick={() => setStrategy(val)}
              disabled={streaming}
            >
              {label}
            </button>
          ))}
          <button
            className={`chip-btn ${useLlmRouter ? 'active' : ''}`}
            onClick={() => setUseLlmRouter((v) => !v)}
            title="Gunakan LLM Router dwibahasa Indonesia -> Inggris"
          >
            <Cpu size={13} style={{ marginRight: 4, verticalAlign: 'middle' }} />
            Router: {useLlmRouter ? 'ON' : 'OFF'}
          </button>
          {messages.length > 0 && (
            <button className="btn" onClick={() => setMessages([])} disabled={streaming}>
              <RotateCcw size={14} /> Reset
            </button>
          )}
        </div>
      </div>

      {messages.length === 0 && (
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          <div style={{ fontSize: '0.82rem', color: '#94a3b8', marginBottom: '0.65rem' }}>
            Klik salah satu skenario populer di bawah ini atau ketik pertanyaan duel Anda sendiri:
          </div>
          <div className="scenario-grid">
            {SCENARIOS.map((sc, i) => (
              <motion.button
                key={i}
                className="scenario-card"
                whileHover={{ y: -4, scale: 1.01 }}
                whileTap={{ scale: 0.99 }}
                onClick={() => sendQuestion(sc.prompt)}
              >
                <span className="badge badge-indigo">{sc.badge}</span>
                <div style={{ fontWeight: 600, fontSize: '0.96rem', color: '#fff', marginTop: '0.2rem' }}>
                  {sc.title}
                </div>
                <div style={{ fontSize: '0.81rem', color: '#94a3b8', lineHeight: 1.5 }}>
                  {sc.subtitle}
                </div>
              </motion.button>
            ))}
          </div>
        </motion.div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
        {messages.map((msg, idx) => (
          <motion.div
            key={idx}
            className="chat-bubble-row"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
          >
            <div className={`chat-avatar ${msg.role}`}>
              {msg.role === 'user' ? <User size={18} /> : <Scale size={18} />}
            </div>
            <div className={`chat-bubble ${msg.role}`}>
              {msg.role === 'assistant' && (
                <TraceAccordion
                  context={msg.context}
                  plan={msg.plan}
                  totalSec={msg.totalSec}
                  onSelectCard={onSelectCard}
                />
              )}

              {msg.role === 'assistant' && idx === messages.length - 1 && liveStage && (
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.55rem',
                    fontSize: '0.84rem',
                    color: '#fbbf24',
                    padding: '0.35rem 0',
                  }}
                >
                  <Sparkles size={16} className="pulse-dot" />
                  <span>{liveStage}</span>
                </div>
              )}

              {msg.content && (
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              )}
            </div>
          </motion.div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form
        className="chat-input-bar"
        onSubmit={(e) => {
          e.preventDefault();
          sendQuestion(input);
        }}
      >
        <input
          className="chat-input-field"
          placeholder="Tanyakan aturan main, interaksi efek kartu, bedah PSCT, atau daftar kartu banned..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={streaming}
        />
        <button className="btn btn-primary" type="submit" disabled={streaming || !input.trim()}>
          <Send size={15} /> {streaming ? 'Memproses...' : 'Kirim'}
        </button>
      </form>
    </div>
  );
}
