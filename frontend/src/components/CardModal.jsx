import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Network, Sparkles, ShieldAlert, Zap } from 'lucide-react';
import HoloCard from './HoloCard.jsx';

export function BanBadge({ format, status }) {
  const st = status || 'Unlimited';
  const cls =
    st === 'Forbidden'
      ? 'badge-forbidden'
      : st === 'Limited'
      ? 'badge-limited'
      : st === 'Semi-Limited'
      ? 'badge-semi'
      : 'badge-unlimited';
  return (
    <span className={`badge ${cls}`}>
      {format}: {st}
    </span>
  );
}

export function PSCTBreakdown({ card }) {
  const psct = card?.psct || {};
  const clauses = psct.clauses || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem' }}>
        <span className="badge badge-indigo">
          <Zap size={12} /> Spell Speed {psct.spell_speed || 1}
        </span>
        <span className={`badge ${psct.has_targeting ? 'badge-limited' : 'badge-unlimited'}`}>
          {psct.has_targeting ? 'Targeting (;)' : 'Non-Targeting'}
        </span>
        <span className={`badge ${psct.has_cost ? 'badge-semi' : 'badge-info'}`}>
          {psct.has_cost ? 'Memiliki Cost (;)' : 'Tanpa Cost (;)'}
        </span>
        {(psct.conjunctions || []).map((conj) => (
          <span key={conj} className="badge badge-info">
            Konjungsi: "{conj}"
          </span>
        ))}
      </div>

      <div
        style={{
          background: '#060a14',
          border: '1px solid rgba(148,163,184,0.16)',
          borderRadius: '10px',
          padding: '0.85rem',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '0.8rem',
          lineHeight: 1.6,
          color: '#cbd5e1',
          whiteSpace: 'pre-wrap',
        }}
      >
        {card?.desc || '-'}
      </div>

      {clauses.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#94a3b8' }}>
            Pembedahan Tata Bahasa PSCT Otomatis ({clauses.length} Klausa):
          </div>
          {clauses.map((cl, idx) => (
            <div key={idx} className="psct-clause-box">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, fontSize: '0.82rem', color: '#e2e8f0' }}>
                  Klausa #{idx + 1}
                </span>
                <span className={`badge ${cl.starts_chain ? 'badge-info' : 'badge-indigo'}`}>
                  {cl.starts_chain ? 'Memulai Chain (: / ;)' : 'Continuous / Material / Non-Chain'}
                </span>
              </div>
              <div style={{ fontSize: '0.81rem', display: 'grid', gap: '0.32rem' }}>
                <div>
                  <span style={{ color: '#fbbf24', fontWeight: 600 }}>Kondisi sebelum (:) → </span>
                  <span style={{ color: '#e2e8f0' }}>
                    {cl.condition || '(Tidak ada syarat aktivasi khusus)'}
                  </span>
                </div>
                <div>
                  <span style={{ color: '#38bdf8', fontWeight: 600 }}>
                    Aktivasi / Cost / Target sebelum (;) →{' '}
                  </span>
                  <span style={{ color: '#e2e8f0' }}>
                    {cl.activation_and_cost || '(Tidak ada tindakan sebelum resolusi)'}
                  </span>
                </div>
                <div>
                  <span style={{ color: '#34d399', fontWeight: 600 }}>Efek saat Resolusi → </span>
                  <span style={{ color: '#f8fafc' }}>{cl.resolution_effect}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function CardModal({ card, onClose, onInspectInGraph }) {
  return (
    <AnimatePresence>
      {card && (
        <motion.div
          className="modal-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="modal-dialog"
            initial={{ opacity: 0, scale: 0.92, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: 16 }}
            transition={{ type: 'spring', stiffness: 340, damping: 28 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                marginBottom: '1.15rem',
                gap: '1rem',
              }}
            >
              <div>
                <h2 style={{ fontSize: '1.35rem', fontWeight: 700, color: '#fff' }}>{card.name}</h2>
                <div style={{ fontSize: '0.84rem', color: '#94a3b8', marginTop: '0.2rem' }}>
                  {card.type} {card.race ? `· ${card.race}` : ''}{' '}
                  {card.attribute ? `· ${card.attribute}` : ''}{' '}
                  {card.archetype ? `· Archetype: ${card.archetype}` : ''}
                </div>
              </div>
              <button className="btn" onClick={onClose} aria-label="Tutup modal">
                <X size={16} /> Tutup
              </button>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(210px, 240px) 1fr',
                gap: '1.5rem',
                alignItems: 'start',
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.85rem' }}>
                <HoloCard imageUrl={card.image_url} name={card.name} width={225} />
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', justifyContent: 'center' }}>
                  <BanBadge format="TCG" status={card.ban_tcg} />
                  <BanBadge format="OCG" status={card.ban_ocg} />
                </div>
                {(card.atk !== null && card.atk !== undefined) && (
                  <div style={{ fontSize: '0.84rem', color: '#cbd5e1', fontWeight: 600 }}>
                    ATK {card.atk} {card.def !== null && card.def !== undefined ? `/ DEF ${card.def}` : ''}
                    {card.linkval ? ` · LINK-${card.linkval}` : ''}
                  </div>
                )}
                {onInspectInGraph && (
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    onClick={() => {
                      onInspectInGraph(card.name);
                      onClose();
                    }}
                  >
                    <Network size={15} /> Buka di Knowledge Graph
                  </button>
                )}
              </div>

              <PSCTBreakdown card={card} />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
