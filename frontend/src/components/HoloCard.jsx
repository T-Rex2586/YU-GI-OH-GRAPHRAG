import React, { useState } from 'react';

export default function HoloCard({ imageUrl, name, width = 220, onClick }) {
  const [style, setStyle] = useState({
    rotateX: 0,
    rotateY: 0,
    glareX: 50,
    glareY: 50,
    active: false,
  });

  const handleMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width;
    const py = (e.clientY - rect.top) / rect.height;
    const rotateY = (px - 0.5) * 24;
    const rotateX = (0.5 - py) * 24;
    setStyle({
      rotateX,
      rotateY,
      glareX: Math.round(px * 100),
      glareY: Math.round(py * 100),
      active: true,
    });
  };

  const handleLeave = () => {
    setStyle({ rotateX: 0, rotateY: 0, glareX: 50, glareY: 50, active: false });
  };

  return (
    <div
      className="holo-card-wrap"
      style={{ width: width ? `${width}px` : '100%', cursor: onClick ? 'pointer' : 'default' }}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      onClick={onClick}
    >
      <div
        className="holo-card-inner"
        style={{
          transform: `rotateX(${style.rotateX}deg) rotateY(${style.rotateY}deg) scale(${
            style.active ? 1.035 : 1
          })`,
        }}
      >
        {imageUrl ? (
          <img src={imageUrl} alt={name} className="holo-card-img" loading="lazy" />
        ) : (
          <div
            style={{
              aspectRatio: '421 / 614',
              display: 'grid',
              placeItems: 'center',
              padding: '1rem',
              textAlign: 'center',
              color: '#94a3b8',
              fontSize: '0.82rem',
            }}
          >
            {name}
          </div>
        )}
        <div
          className="holo-foil-overlay"
          style={{
            opacity: style.active ? 0.65 : 0,
            background: `
              radial-gradient(circle at ${style.glareX}% ${style.glareY}%, rgba(255,255,255,0.65) 0%, transparent 52%),
              linear-gradient(125deg, rgba(99,102,241,0.32) 10%, rgba(236,72,153,0.3) 35%, rgba(251,191,36,0.32) 60%, rgba(52,211,153,0.3) 85%)
            `,
          }}
        />
      </div>
    </div>
  );
}
