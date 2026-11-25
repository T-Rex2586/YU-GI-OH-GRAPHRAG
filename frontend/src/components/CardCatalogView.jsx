import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Search,
  LayoutGrid,
  Table as TableIcon,
  ChevronLeft,
  ChevronRight,
  Network,
  ShieldAlert,
  Maximize2,
} from 'lucide-react';
import HoloCard from './HoloCard.jsx';
import { BanBadge, PSCTBreakdown } from './CardModal.jsx';

export default function CardCatalogView({ onOpenModal, onInspectInGraph }) {
  const [subTab, setSubTab] = useState('catalog'); // 'catalog' | 'banlist'

  // Catalog state
  const [search, setSearch] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [category, setCategory] = useState('all');
  const [banFilter, setBanFilter] = useState('all');
  const [layoutMode, setLayoutMode] = useState('split'); // 'split' (Table + Live Inspector) | 'grid' (3D Holo Grid)
  const [page, setPage] = useState(1);
  const [catalogResp, setCatalogResp] = useState({ total: 0, total_pages: 1, items: [] });
  const [activeCard, setActiveCard] = useState(null);
  const [loading, setLoading] = useState(false);

  // Banlist state
  const [banFormat, setBanFormat] = useState('TCG');
  const [banStatus, setBanStatus] = useState('all');
  const [banSearch, setBanSearch] = useState('');
  const [banData, setBanData] = useState({ total: 0, summary: {}, items: [] });

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQ(search);
      setPage(1);
    }, 200);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (subTab !== 'catalog') return;
    let cancelled = false;
    setLoading(true);
    const url = `/api/cards?q=${encodeURIComponent(debouncedQ)}&category=${category}&ban_tcg=${banFilter}&page=${page}&page_size=24`;
    fetch(url)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setCatalogResp(data);
        if (data.items?.length > 0) {
          setActiveCard((prev) => {
            if (prev && data.items.some((x) => x.id === prev.id)) return prev;
            return data.items[0];
          });
        } else {
          setActiveCard(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [subTab, debouncedQ, category, banFilter, page]);

  useEffect(() => {
    if (subTab !== 'banlist') return;
    fetch(
      `/api/banlist?format=${banFormat}&status=${banStatus}&q=${encodeURIComponent(banSearch)}`
    )
      .then((r) => r.json())
      .then((data) => setBanData(data));
  }, [subTab, banFormat, banStatus, banSearch]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.15rem' }}>
      {/* Sub-navigation header */}
      <div
        className="glass-panel"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.85rem',
        }}
      >
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            className={`btn ${subTab === 'catalog' ? 'btn-primary' : ''}`}
            onClick={() => setSubTab('catalog')}
          >
            Katalog 14.704 Kartu & Bedah PSCT
          </button>
          <button
            className={`btn ${subTab === 'banlist' ? 'btn-primary' : ''}`}
            onClick={() => setSubTab('banlist')}
          >
            <ShieldAlert size={15} /> Daftar Forbidden & Limited (Banlist)
          </button>
        </div>

        {subTab === 'catalog' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', color: '#94a3b8', marginRight: '0.25rem' }}>
              Ditemukan <strong style={{ color: '#fff' }}>{catalogResp.total.toLocaleString()}</strong> kartu
            </span>
            <button
              className={`chip-btn ${layoutMode === 'split' ? 'active' : ''}`}
              onClick={() => setLayoutMode('split')}
            >
              <TableIcon size={13} style={{ marginRight: 4, verticalAlign: 'middle' }} />
              Tabel + Live PSCT
            </button>
            <button
              className={`chip-btn ${layoutMode === 'grid' ? 'active' : ''}`}
              onClick={() => setLayoutMode('grid')}
            >
              <LayoutGrid size={13} style={{ marginRight: 4, verticalAlign: 'middle' }} />
              Galeri 3D Foil
            </button>
          </div>
        )}
      </div>

      {subTab === 'catalog' ? (
        <>
          {/* Filter Bar */}
          <div
            className="glass-panel"
            style={{
              display: 'grid',
              gridTemplateColumns: '1.8fr 1.1fr auto',
              gap: '0.85rem',
              alignItems: 'center',
            }}
          >
            <div style={{ position: 'relative' }}>
              <Search
                size={16}
                color="#64748b"
                style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }}
              />
              <input
                className="input-box"
                style={{ paddingLeft: '2.25rem' }}
                placeholder="Cari dari seluruh 14.704 kartu (nama, archetype, race, atau efek)..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <select
              className="select-box"
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(1);
              }}
            >
              <option value="all">Semua Kategori Kartu</option>
              <option value="monster">Main Deck Monster</option>
              <option value="extradeck">Extra Deck (Fusion / Synchro / Xyz / Link)</option>
              <option value="spell">Spell Card</option>
              <option value="trap">Trap Card</option>
            </select>

            <div className="pill-row">
              {[
                ['all', 'Semua'],
                ['Forbidden', 'Forbidden'],
                ['Limited', 'Limited'],
                ['Semi-Limited', 'Semi-Limited'],
              ].map(([val, label]) => (
                <button
                  key={val}
                  className={`chip-btn ${banFilter === val ? 'active' : ''}`}
                  onClick={() => {
                    setBanFilter(val);
                    setPage(1);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {layoutMode === 'split' ? (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'minmax(420px, 1.1fr) minmax(420px, 1.25fr)',
                gap: '1.15rem',
                alignItems: 'start',
              }}
            >
              {/* Klik baris langsung instan mengganti activeCard! */}
              <div className="glass-panel" style={{ padding: '0.85rem' }}>
                <div className="data-table-wrap" style={{ maxHeight: 580, overflowY: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Nama Kartu</th>
                        <th>Tipe</th>
                        <th>TCG</th>
                        <th>SS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {catalogResp.items.map((c) => {
                        const isSel = activeCard?.id === c.id;
                        return (
                          <tr
                            key={c.id}
                            className={`clickable-row ${isSel ? 'selected' : ''}`}
                            onClick={() => setActiveCard(c)}
                          >
                            <td style={{ fontWeight: 600, color: isSel ? '#fff' : '#e2e8f0' }}>
                              {c.name}
                              {c.archetype && (
                                <div style={{ fontSize: '0.72rem', color: '#64748b', fontWeight: 400 }}>
                                  {c.archetype}
                                </div>
                              )}
                            </td>
                            <td style={{ color: '#94a3b8', fontSize: '0.78rem' }}>{c.type}</td>
                            <td>
                              <BanBadge format="TCG" status={c.ban_tcg} />
                            </td>
                            <td style={{ color: '#38bdf8', fontWeight: 600 }}>
                              {c.psct?.spell_speed || 1}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* Pagination */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginTop: '0.85rem',
                  }}
                >
                  <button
                    className="btn"
                    disabled={page <= 1 || loading}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    <ChevronLeft size={15} /> Sebelumnya
                  </button>
                  <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                    Halaman <strong style={{ color: '#fff' }}>{catalogResp.page}</strong> dari{' '}
                    {catalogResp.total_pages.toLocaleString()}
                  </span>
                  <button
                    className="btn"
                    disabled={page >= catalogResp.total_pages || loading}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Berikutnya <ChevronRight size={15} />
                  </button>
                </div>
              </div>

              {/* Live Animated Card + PSCT Inspector */}
              {activeCard && (
                <motion.div
                  key={activeCard.id}
                  className="glass-panel"
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22 }}
                  style={{ display: 'grid', gap: '1.1rem' }}
                >
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '165px 1fr',
                      gap: '1.15rem',
                      alignItems: 'start',
                    }}
                  >
                    <HoloCard
                      imageUrl={activeCard.image_url}
                      name={activeCard.name}
                      width={165}
                      onClick={() => onOpenModal(activeCard)}
                    />
                    <div style={{ display: 'grid', gap: '0.55rem' }}>
                      <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#fff' }}>
                        {activeCard.name}
                      </h2>
                      <div style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                        {activeCard.type} {activeCard.race ? `· ${activeCard.race}` : ''}{' '}
                        {activeCard.attribute ? `· ${activeCard.attribute}` : ''}
                      </div>
                      {activeCard.archetype && (
                        <div style={{ fontSize: '0.8rem', color: '#fbbf24' }}>
                          Archetype: <strong>{activeCard.archetype}</strong>
                        </div>
                      )}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                        <BanBadge format="TCG" status={activeCard.ban_tcg} />
                        <BanBadge format="OCG" status={activeCard.ban_ocg} />
                      </div>
                      {activeCard.atk !== null && activeCard.atk !== undefined && (
                        <div style={{ fontSize: '0.84rem', fontWeight: 600, color: '#e2e8f0' }}>
                          ATK {activeCard.atk}{' '}
                          {activeCard.def !== null && activeCard.def !== undefined
                            ? `/ DEF ${activeCard.def}`
                            : ''}
                          {activeCard.linkval ? ` · LINK-${activeCard.linkval}` : ''}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
                        <button
                          className="btn btn-primary"
                          onClick={() => onInspectInGraph(activeCard.name)}
                        >
                          <Network size={14} /> Lihat di Graph
                        </button>
                        <button className="btn" onClick={() => onOpenModal(activeCard)}>
                          <Maximize2 size={14} /> Layar Penuh
                        </button>
                      </div>
                    </div>
                  </div>

                  <PSCTBreakdown card={activeCard} />
                </motion.div>
              )}
            </div>
          ) : (
            <>
              <div className="cards-grid">
                {catalogResp.items.map((c) => (
                  <motion.div
                    key={c.id}
                    className="catalog-card-tile"
                    whileHover={{ y: -5 }}
                    onClick={() => onOpenModal(c)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'center' }}>
                      <HoloCard imageUrl={c.image_url_small || c.image_url} name={c.name} width={155} />
                    </div>
                    <div
                      style={{
                        fontWeight: 600,
                        fontSize: '0.82rem',
                        color: '#f8fafc',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {c.name}
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <BanBadge format="TCG" status={c.ban_tcg} />
                      <span style={{ fontSize: '0.72rem', color: '#38bdf8' }}>
                        SS {c.psct?.spell_speed || 1}
                      </span>
                    </div>
                  </motion.div>
                ))}
              </div>

              <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '1rem' }}>
                <button
                  className="btn"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  <ChevronLeft size={15} /> Sebelumnya
                </button>
                <span style={{ fontSize: '0.84rem', color: '#94a3b8' }}>
                  Halaman <strong style={{ color: '#fff' }}>{catalogResp.page}</strong> /{' '}
                  {catalogResp.total_pages.toLocaleString()}
                </span>
                <button
                  className="btn"
                  disabled={page >= catalogResp.total_pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Berikutnya <ChevronRight size={15} />
                </button>
              </div>
            </>
          )}
        </>
      ) : (
        /* BANLIST VIEW */
        <div style={{ display: 'grid', gap: '1.15rem' }}>
          <div className="kpi-grid">
            {['Forbidden', 'Limited', 'Semi-Limited'].map((stName) => {
              const count = banData.summary?.[banFormat]?.[stName] || 0;
              const color =
                stName === 'Forbidden' ? '#ef4444' : stName === 'Limited' ? '#f59e0b' : '#a855f7';
              return (
                <div key={stName} className="glass-panel" style={{ borderLeft: `4px solid ${color}` }}>
                  <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                    {stName} ({banFormat})
                  </div>
                  <div style={{ fontSize: '1.9rem', fontWeight: 700, color: '#fff', marginTop: '0.2rem' }}>
                    {count}
                  </div>
                  <div style={{ fontSize: '0.74rem', color: '#64748b' }}>
                    Maksimum {stName === 'Forbidden' ? '0' : stName === 'Limited' ? '1' : '2'} copy di Deck
                  </div>
                </div>
              );
            })}
          </div>

          <div
            className="glass-panel"
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '0.8rem',
            }}
          >
            <div className="pill-row">
              {['TCG', 'OCG', 'Goat'].map((fmt) => (
                <button
                  key={fmt}
                  className={`chip-btn ${banFormat === fmt ? 'active' : ''}`}
                  onClick={() => setBanFormat(fmt)}
                >
                  Format {fmt}
                </button>
              ))}
            </div>

            <div className="pill-row">
              {[
                ['all', 'Semua Status'],
                ['Forbidden', 'Forbidden (0)'],
                ['Limited', 'Limited (1)'],
                ['Semi-Limited', 'Semi-Limited (2)'],
              ].map(([val, label]) => (
                <button
                  key={val}
                  className={`chip-btn ${banStatus === val ? 'active' : ''}`}
                  onClick={() => setBanStatus(val)}
                >
                  {label}
                </button>
              ))}
            </div>

            <input
              className="input-box"
              style={{ maxWidth: 280 }}
              placeholder="Filter nama kartu banned..."
              value={banSearch}
              onChange={(e) => setBanSearch(e.target.value)}
            />
          </div>

          <div className="cards-grid">
            {banData.items.slice(0, 96).map((b) => (
              <motion.div
                key={`${b.format}_${b.card_id}`}
                className="catalog-card-tile"
                whileHover={{ y: -5 }}
                onClick={() =>
                  onOpenModal({
                    ...b,
                    id: b.card_id,
                    name: b.card_name,
                    type: b.card_type,
                  })
                }
              >
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <HoloCard imageUrl={b.image_url_small || b.image_url} name={b.card_name} width={150} />
                </div>
                <div
                  style={{
                    fontWeight: 600,
                    fontSize: '0.81rem',
                    color: '#fff',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {b.card_name}
                </div>
                <BanBadge format={b.format} status={b.status} />
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
