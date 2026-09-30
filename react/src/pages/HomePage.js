import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';

function HomePage() {
  const navigate = useNavigate();
  const [hovered, setHovered] = useState(null);

  const baseBtn = {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '1.2rem 2.8rem',
    borderRadius: '0.9rem',
    fontSize: '2rem',
    fontWeight: '600',
    letterSpacing: '0.05em',
    border: 'none',
    cursor: 'pointer',
    overflow: 'hidden',
    transition: 'all 0.35s cubic-bezier(0.22, 1, 0.36, 1)',
    whiteSpace: 'nowrap',
    fontFamily: 'inherit',
    flex: 1,
  };

  const primaryBtn = {
    ...baseBtn,
    background: 'linear-gradient(135deg, #A9714B, #7A4E2E)',
    color: '#FFF8F0',
    boxShadow: '0 10px 24px rgba(122, 78, 46, 0.35), inset 0 1px 0 rgba(255,255,255,0.25)',
  };

  const glassBtn = {
    ...baseBtn,
    background: 'rgba(255, 255, 255, 0.55)',
    color: '#6B4A2E',
    border: '1px solid rgba(139, 94, 60, 0.35)',
    backdropFilter: 'blur(10px)',
    WebkitBackdropFilter: 'blur(10px)',
    boxShadow: '0 8px 20px rgba(255, 139, 77, 0.18), inset 0 1px 0 rgba(255,255,255,0.8)',
  };

  const shine = {
    position: 'absolute',
    top: 0,
    left: '-75%',
    width: '50%',
    height: '100%',
    background:
      'linear-gradient(120deg, transparent 0%, rgba(255,255,255,0.55) 50%, transparent 100%)',
    transform: 'skewX(-20deg)',
    transition: 'left 0.7s cubic-bezier(0.22, 1, 0.36, 1)',
    pointerEvents: 'none',
  };

  const buttons = [
    { key: 'stations', label: '沉浸式研学', route: '/stations', icon: '🗺️' },
    { key: 'qa', label: '侨乡故事问答', route: '/intelligent-qa', icon: '📖' },
    { key: 'route', label: '鮀城漫游', route: '/route-planner', icon: '🚶' },
  ];

  return (
    <div style={{ position: 'relative', minHeight: '100vh' }}>
      {/* 背景图片 */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 0 }}>
        <img
          src="./home.png"
          alt="背景"
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.1)',
          }}
        ></div>
      </div>

      {/* 内容区域：屏幕正中间 */}
      <div
        style={{
          position: 'absolute',
          zIndex: 10,
          top: '50%',
          left: '40%',
          transform: 'translate(-50%, -50%)',
          padding: '0 1rem',
          width: '100%',
          maxWidth: '1200px',
        }}
      >
        <div
          style={{
            display: 'flex',
            flexDirection: 'row',
            flexWrap: 'nowrap',
            justifyContent: 'center',
            gap: '1.5rem',
            width: '100%',
            maxWidth: '1100px',
            margin: '0 auto',
          }}
        >
          {buttons.map((btn) => {
            const isHover = hovered === btn.key;
            const style = {
              ...(btn.primary ? primaryBtn : glassBtn),
              transform: isHover
                ? 'translateY(-4px) scale(1.03)'
                : 'translateY(0) scale(1)',
              boxShadow: btn.primary
                ? isHover
                  ? '0 16px 32px rgba(255, 139, 77, 0.5), inset 0 1px 0 rgba(255,255,255,0.5)'
                  : primaryBtn.boxShadow
                : isHover
                ? '0 14px 28px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255,255,255,0.7)'
                : glassBtn.boxShadow,
              background:
                !btn.primary && isHover
                  ? 'linear-gradient(135deg, rgba(255,166,92,0.95), rgba(242,112,58,0.95))'
                  : btn.primary
                  ? primaryBtn.background
                  : glassBtn.background,
              color: !btn.primary && isHover ? '#fff' : btn.primary ? '#fff' : glassBtn.color,
            };

            return (
              <button
                key={btn.key}
                onClick={() => navigate(btn.route)}
                onMouseEnter={() => setHovered(btn.key)}
                onMouseLeave={() => setHovered(null)}
                style={style}
              >
                <span style={{ ...shine, left: isHover ? '125%' : '-75%' }} />

                <span
                  style={{
                    position: 'relative',
                    zIndex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '1.8rem',
                    flexShrink: 0,
                    marginRight: '0.6rem',
                    transition: 'all 0.35s cubic-bezier(0.22, 1, 0.36, 1)',
                    transform: isHover
                      ? 'scale(1.12) rotate(-6deg)'
                      : 'scale(1) rotate(0)',
                  }}
                >
                  {btn.icon}
                </span>

                <span style={{ position: 'relative', zIndex: 1 }}>{btn.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default HomePage;