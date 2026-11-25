import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Search, ZoomIn, ZoomOut, Maximize2, Sparkles } from 'lucide-react';
import HoloCard from './HoloCard.jsx';
import { BanBadge } from './CardModal.jsx';

const PRESET_ENTITIES = [
  'Ash Blossom & Joyous Spring',
  'Mirrorjade the Iceblade Dragon',
  'Fallen of Albaz',
  'Baronne de Fleur',
  'Dark Magician',
  'Blue-Eyes White Dragon',
  'Infinite Impermanence',
];

const CATEGORY_COLORS = {
  Card: '#818cf8',
  Archetype: '#fbbf24',
  Ruling: '#34d399',
  CardFAQ: '#2dd4bf',
  PSCTRule: '#c084fc',
  GameConcept: '#38bdf8',
  RuleChunk: '#fb923c',
  Format: '#f87171',
  BanStatus: '#ef4444',
  Attribute: '#a3e635',
  MonsterRace: '#f472b6',
  CardType: '#94a3b8',
};

export default function GraphExplorerView({ initialQuery, onSelectCard }) {
  const [query, setQuery] = useState(initialQuery || 'Ash Blossom & Joyous Spring');
  const [searchBox, setSearchBox] = useState(initialQuery || 'Ash Blossom & Joyous Spring');
  const [hop, setHop] = useState(1);
  const [maxEdges, setMaxEdges] = useState(50);
  const [graphData, setGraphData] = useState({ nodes: [], links: [], source: '' });
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);

  const canvasRef = useRef(null);
  const simRef = useRef({
    nodes: [],
    links: [],
    transform: { x: 0, y: 0, k: 1 },
    hoveredId: null,
    draggingNode: null,
    panning: false,
    lastMouse: { x: 0, y: 0 },
    tick: 0,
  });

  useEffect(() => {
    if (initialQuery && initialQuery !== query) {
      setSearchBox(initialQuery);
      setQuery(initialQuery);
    }
  }, [initialQuery]);

  // Fetch subgraph whenever query, hop, or maxEdges changes
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/graph?q=${encodeURIComponent(query)}&hop=${hop}&limit=${maxEdges}`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setGraphData(data);
        setSelectedNode(data.nodes?.[0] || null);

        // Initialize 2D force simulation positions
        const W = canvasRef.current?.clientWidth || 900;
        const H = 560;
        const cx = W / 2;
        const cy = H / 2;

        const simNodes = (data.nodes || []).map((n, idx) => {
          const angle = (idx / Math.max(1, data.nodes.length)) * Math.PI * 2;
          const dist = idx === 0 ? 0 : 120 + (idx % 3) * 55;
          return {
            ...n,
            x: cx + Math.cos(angle) * dist,
            y: cy + Math.sin(angle) * dist,
            vx: 0,
            vy: 0,
            radius: idx === 0 ? 18 : n.categoryName === 'Card' ? 13 : 10,
            color: CATEGORY_COLORS[n.categoryName] || '#818cf8',
            pinned: idx === 0,
          };
        });

        const nodeMap = new Map(simNodes.map((n) => [n.id, n]));
        const simLinks = (data.links || [])
          .map((l) => ({
            ...l,
            sourceNode: nodeMap.get(l.source),
            targetNode: nodeMap.get(l.target),
          }))
          .filter((l) => l.sourceNode && l.targetNode);

        simRef.current.nodes = simNodes;
        simRef.current.links = simLinks;
        simRef.current.transform = { x: 0, y: 0, k: 1 };
        simRef.current.alpha = 1.0;
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [query, hop, maxEdges]);

  // 60fps Force-Directed Physics & Particle Renderer
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animId;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.parentElement.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = 560 * dpr;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = '560px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);

    const renderLoop = () => {
      const sim = simRef.current;
      const W = canvas.clientWidth || 900;
      const H = 560;
      sim.tick += 1;

      const nodes = sim.nodes;
      const links = sim.links;

      // Force step
      if (sim.alpha > 0.015) {
        // Repulsion
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i];
            const b = nodes[j];
            let dx = b.x - a.x;
            let dy = b.y - a.y;
            let d2 = dx * dx + dy * dy + 1;
            const force = (2200 * sim.alpha) / d2;
            const d = Math.sqrt(d2);
            const fx = (dx / d) * force;
            const fy = (dy / d) * force;
            if (!a.pinned) {
              a.vx -= fx;
              a.vy -= fy;
            }
            if (!b.pinned) {
              b.vx += fx;
              b.vy += fy;
            }
          }
        }

        // Spring attraction along edges
        for (const l of links) {
          const s = l.sourceNode;
          const t = l.targetNode;
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const targetLen = hop === 1 ? 155 : 125;
          const kSpring = 0.045 * sim.alpha;
          const f = (dist - targetLen) * kSpring;
          const fx = (dx / dist) * f;
          const fy = (dy / dist) * f;
          if (!s.pinned) {
            s.vx += fx;
            s.vy += fy;
          }
          if (!t.pinned) {
            t.vx -= fx;
            t.vy -= fy;
          }
        }

        // Gentle center gravity & velocity integration
        for (const n of nodes) {
          if (n.pinned || n === sim.draggingNode) continue;
          n.vx += (W / 2 - n.x) * 0.003 * sim.alpha;
          n.vy += (H / 2 - n.y) * 0.003 * sim.alpha;
          n.vx *= 0.82;
          n.vy *= 0.82;
          n.x += n.vx;
          n.y += n.vy;
        }
        sim.alpha *= 0.99;
      }

      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.translate(sim.transform.x, sim.transform.y);
      ctx.scale(sim.transform.k, sim.transform.k);

      const hov = sim.hoveredId;
      const connectedSet = new Set();
      if (hov) {
        connectedSet.add(hov);
        for (const l of links) {
          if (l.source === hov) connectedSet.add(l.target);
          if (l.target === hov) connectedSet.add(l.source);
        }
      }

      // Draw edges + animated flowing particles
      const particleOffset = (sim.tick % 90) / 90;
      for (const l of links) {
        const s = l.sourceNode;
        const t = l.targetNode;
        const highlighted = !hov || (connectedSet.has(s.id) && connectedSet.has(t.id));

        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.strokeStyle = highlighted ? 'rgba(148, 163, 184, 0.42)' : 'rgba(71, 85, 105, 0.12)';
        ctx.lineWidth = highlighted && hov ? 2 : 1.25;
        ctx.stroke();

        // Flowing energy particle
        if (highlighted) {
          const px = s.x + (t.x - s.x) * particleOffset;
          const py = s.y + (t.y - s.y) * particleOffset;
          ctx.beginPath();
          ctx.arc(px, py, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = t.color;
          ctx.fill();
        }

        // Edge relation label on hover
        if (hov && (s.id === hov || t.id === hov)) {
          const mx = (s.x + t.x) / 2;
          const my = (s.y + t.y) / 2;
          ctx.font = '500 9.5px Inter, sans-serif';
          ctx.fillStyle = '#fbbf24';
          ctx.textAlign = 'center';
          ctx.fillText(l.value, mx, my - 4);
        }
      }

      // Draw nodes
      for (const n of nodes) {
        const dimmed = hov && !connectedSet.has(n.id);
        ctx.globalAlpha = dimmed ? 0.22 : 1;

        // Outer neon halo
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius + 5, 0, Math.PI * 2);
        ctx.fillStyle = `${n.color}28`;
        ctx.fill();

        // Core circle
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
        ctx.fillStyle = n.color;
        ctx.fill();
        ctx.lineWidth = selectedNode?.id === n.id ? 3 : 1.5;
        ctx.strokeStyle = selectedNode?.id === n.id ? '#ffffff' : '#090d16';
        ctx.stroke();

        // Node label
        ctx.font = `${n.pinned ? '600 12px' : '500 10.5px'} Inter, sans-serif`;
        ctx.fillStyle = '#f1f5f9';
        ctx.textAlign = 'left';
        ctx.fillText(n.name, n.x + n.radius + 6, n.y + 3.5);
      }

      ctx.globalAlpha = 1;
      ctx.restore();
      animId = requestAnimationFrame(renderLoop);
    };

    animId = requestAnimationFrame(renderLoop);
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, [hop, selectedNode]);

  // Pointer Helpers
  const toWorld = (clientX, clientY) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const { x, y, k } = simRef.current.transform;
    return {
      wx: (clientX - rect.left - x) / k,
      wy: (clientY - rect.top - y) / k,
    };
  };

  const findNodeAt = (wx, wy) => {
    const nodes = simRef.current.nodes;
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      const dx = wx - n.x;
      const dy = wy - n.y;
      if (dx * dx + dy * dy <= (n.radius + 5) ** 2) return n;
    }
    return null;
  };

  const onMouseDown = (e) => {
    const { wx, wy } = toWorld(e.clientX, e.clientY);
    const hit = findNodeAt(wx, wy);
    simRef.current.lastMouse = { x: e.clientX, y: e.clientY };
    if (hit) {
      simRef.current.draggingNode = hit;
      simRef.current.alpha = 0.5;
      setSelectedNode(hit);
    } else {
      simRef.current.panning = true;
    }
  };

  const onMouseMove = (e) => {
    const sim = simRef.current;
    const { wx, wy } = toWorld(e.clientX, e.clientY);
    if (sim.draggingNode) {
      sim.draggingNode.x = wx;
      sim.draggingNode.y = wy;
      sim.alpha = 0.35;
      return;
    }
    if (sim.panning) {
      sim.transform.x += e.clientX - sim.lastMouse.x;
      sim.transform.y += e.clientY - sim.lastMouse.y;
      sim.lastMouse = { x: e.clientX, y: e.clientY };
      return;
    }
    const hit = findNodeAt(wx, wy);
    sim.hoveredId = hit ? hit.id : null;
    canvasRef.current.style.cursor = hit ? 'pointer' : 'grab';
  };

  const onMouseUp = () => {
    simRef.current.draggingNode = null;
    simRef.current.panning = false;
  };

  const onDoubleClick = (e) => {
    const { wx, wy } = toWorld(e.clientX, e.clientY);
    const hit = findNodeAt(wx, wy);
    if (hit && hit.fullName) {
      setSearchBox(hit.fullName);
      setQuery(hit.fullName);
    }
  };

  const onWheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.12 : 0.9;
    const nextK = Math.min(2.6, Math.max(0.42, simRef.current.transform.k * factor));
    simRef.current.transform.k = nextK;
  };

  const handleSelectPreset = (entity) => {
    setSearchBox(entity);
    setQuery(entity);
  };

  const activeCategories = Array.from(new Set((graphData.nodes || []).map((n) => n.categoryName)));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
      <div className="glass-panel" style={{ display: 'grid', gap: '0.95rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <h1 style={{ fontSize: '1.3rem', fontWeight: 700 }}>Eksplorasi Jaringan Knowledge Graph</h1>
            <p style={{ fontSize: '0.82rem', color: '#94a3b8', marginTop: '0.15rem' }}>
              Klik entitas populer di bawah, seret node, arahkan kursor untuk sorot relasi, atau klik dua kali node untuk memusatkan graf baru.
            </p>
          </div>
          <span className="badge badge-indigo">
            {graphData.source || 'Neo4j Graph'} · {graphData.nodes?.length || 0} Node · {graphData.links?.length || 0} Relasi
          </span>
        </div>

        <div className="pill-row">
          {PRESET_ENTITIES.map((ent) => (
            <button
              key={ent}
              type="button"
              className={`chip-btn ${query === ent ? 'active' : ''}`}
              onClick={() => handleSelectPreset(ent)}
            >
              {ent}
            </button>
          ))}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (searchBox.trim()) setQuery(searchBox.trim());
          }}
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto auto auto',
            gap: '0.7rem',
            alignItems: 'center',
          }}
        >
          <input
            className="input-box"
            value={searchBox}
            onChange={(e) => setSearchBox(e.target.value)}
            placeholder="Ketik nama kartu, archetype, atau mekanik (misal: Tearlaments, Synchro Summon)..."
          />
          <div style={{ display: 'flex', gap: '0.35rem' }}>
            {[1, 2].map((h) => (
              <button
                key={h}
                type="button"
                className={`chip-btn ${hop === h ? 'active' : ''}`}
                onClick={() => setHop(h)}
              >
                {h}-Hop
              </button>
            ))}
          </div>
          <select
            className="select-box"
            style={{ width: 135 }}
            value={maxEdges}
            onChange={(e) => setMaxEdges(Number(e.target.value))}
          >
            <option value={30}>30 Relasi</option>
            <option value={50}>50 Relasi</option>
            <option value={80}>80 Relasi</option>
            <option value={110}>110 Relasi</option>
          </select>
          <button type="submit" className="btn btn-primary">
            <Search size={15} /> Telusuri
          </button>
        </form>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: selectedNode ? '1fr 310px' : '1fr',
          gap: '1.1rem',
          alignItems: 'start',
        }}
      >
        <div className="glass-panel" style={{ padding: '0.75rem', position: 'relative', overflow: 'hidden' }}>
          {/* Legend & Zoom Controls */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.5rem',
              padding: '0.25rem 0.5rem 0.65rem',
            }}
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.65rem' }}>
              {activeCategories.map((cat) => (
                <span key={cat} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: '#cbd5e1' }}>
                  <span
                    style={{
                      width: 9,
                      height: 9,
                      borderRadius: '50%',
                      background: CATEGORY_COLORS[cat] || '#818cf8',
                    }}
                  />
                  {cat}
                </span>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '0.35rem' }}>
              <button
                className="btn"
                style={{ padding: '0.35rem 0.55rem' }}
                onClick={() => (simRef.current.transform.k = Math.min(2.5, simRef.current.transform.k * 1.2))}
                title="Perbesar"
              >
                <ZoomIn size={14} />
              </button>
              <button
                className="btn"
                style={{ padding: '0.35rem 0.55rem' }}
                onClick={() => (simRef.current.transform.k = Math.max(0.45, simRef.current.transform.k * 0.82))}
                title="Perkecil"
              >
                <ZoomOut size={14} />
              </button>
              <button
                className="btn"
                style={{ padding: '0.35rem 0.55rem' }}
                onClick={() => {
                  simRef.current.transform = { x: 0, y: 0, k: 1 };
                  simRef.current.alpha = 0.6;
                }}
                title="Reset posisi"
              >
                <Maximize2 size={14} />
              </button>
            </div>
          </div>

          <div style={{ position: 'relative', background: '#050811', borderRadius: '12px', overflow: 'hidden' }}>
            {loading && (
              <div
                style={{
                  position: 'absolute',
                  top: 12,
                  right: 14,
                  zIndex: 5,
                  fontSize: '0.78rem',
                  color: '#fbbf24',
                }}
              >
                Memuat sub-graf Neo4j...
              </div>
            )}
            <canvas
              ref={canvasRef}
              onMouseDown={onMouseDown}
              onMouseMove={onMouseMove}
              onMouseUp={onMouseUp}
              onMouseLeave={onMouseUp}
              onDoubleClick={onDoubleClick}
              onWheel={onWheel}
            />
          </div>
        </div>

        {selectedNode && (
          <motion.div
            key={selectedNode.id}
            className="glass-panel"
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}
          >
            <div>
              <span
                className="badge"
                style={{
                  background: `${CATEGORY_COLORS[selectedNode.categoryName] || '#818cf8'}25`,
                  color: CATEGORY_COLORS[selectedNode.categoryName] || '#818cf8',
                  border: `1px solid ${CATEGORY_COLORS[selectedNode.categoryName] || '#818cf8'}66`,
                }}
              >
                {selectedNode.categoryName}
              </span>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginTop: '0.45rem', color: '#fff' }}>
                {selectedNode.fullName || selectedNode.name}
              </h3>
            </div>

            {selectedNode.card ? (
              <>
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <HoloCard
                    imageUrl={selectedNode.card.image_url}
                    name={selectedNode.card.name}
                    width={175}
                    onClick={() => onSelectCard(selectedNode.card)}
                  />
                </div>
                <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', justifyContent: 'center' }}>
                  <BanBadge format="TCG" status={selectedNode.card.ban_tcg} />
                  <BanBadge format="OCG" status={selectedNode.card.ban_ocg} />
                </div>
                <button
                  className="btn btn-primary"
                  style={{ width: '100%', justifyContent: 'center' }}
                  onClick={() => onSelectCard(selectedNode.card)}
                >
                  <Sparkles size={14} /> Bedah PSCT & Detail Kartu
                </button>
              </>
            ) : (
              <p style={{ fontSize: '0.82rem', color: '#94a3b8', lineHeight: 1.55 }}>
                Node bertipe <strong>{selectedNode.categoryName}</strong> dalam jaringan Knowledge Graph Yu-Gi-Oh!.
              </p>
            )}

            <button
              className="btn"
              style={{ width: '100%', justifyContent: 'center' }}
              onClick={() => {
                const targetQ = selectedNode.fullName || selectedNode.name;
                setSearchBox(targetQ);
                setQuery(targetQ);
              }}
            >
              Jadikan Pusat Sub-Graf
            </button>
          </motion.div>
        )}
      </div>
    </div>
  );
}
