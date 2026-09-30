import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

// 5个站点配置（pos 是地图上的百分比坐标，按地图实际位置微调）
const STATIONS = [
  { id: 1, name: '上盐村', title: '郑正秋故居', pos: { x: 25, y: 70 }, color: '#FF8B4D' },
  { id: 2, name: '东盐村', title: '粿品工坊',   pos: { x: 40, y: 60 }, color: '#E8A87C' },
  { id: 3, name: '大寮村', title: '嵌瓷工艺社', pos: { x: 58, y: 75 }, color: '#C38D9E' },
  { id: 4, name: '文化公园', title: '华侨名人展', pos: { x: 78, y: 40 }, color: '#85586F' },
  { id: 5, name: '田中央', title: '侨批局',    pos: { x: 60, y: 20 }, color: '#6B4226' },
];

function StationsPage() {
  const navigate = useNavigate();
  const [progress, setProgress] = useState({});
  const [money, setMoney] = useState(0);
  const [items, setItems] = useState([]);

  useEffect(() => {
    const saved = localStorage.getItem('qiaoxiang_progress');
    if (saved) {
      const data = JSON.parse(saved);
      setProgress(data.stations || {});
      setMoney(data.money || 0);
      setItems(data.items || []);
    }
  }, []);

  // 当前站 = 第一个未完成的站
  const currentStationId = (() => {
    for (const s of STATIONS) {
      if (!progress[s.id]?.done) return s.id;
    }
    return null;
  })();

  const handleStationClick = (station) => {
    if (station.id === currentStationId || progress[station.id]?.done) {
      navigate(`/stations/${station.id}`);
    }
  };

  const doneCount = STATIONS.filter(s => progress[s.id]?.done).length;

  // 撤销：把最后一个已完成的站点变回未完成
  const undoLastStation = () => {
    const doneIds = STATIONS
      .filter(s => progress[s.id]?.done)
      .map(s => s.id);
    if (doneIds.length === 0) {
      alert('没有可撤销的完成记录');
      return;
    }
    const lastId = doneIds[doneIds.length - 1];   // 最后一个完成的
    const nextStations = { ...progress };
    delete nextStations[lastId];

    const saved = JSON.parse(localStorage.getItem('qiaoxiang_progress') || '{}');
    const next = { ...saved, stations: nextStations };
    localStorage.setItem('qiaoxiang_progress', JSON.stringify(next));
    setProgress(nextStations);
  };

  // 重置：清空所有站点进度 + 钱 + 道具
  const resetAllProgress = () => {
    if (!window.confirm('确定要清空所有进度吗？（站点、大洋、道具全部重置）')) return;
    try {
      localStorage.setItem('qiaoxiang_progress', JSON.stringify({
        stations: {},
        money: 0,
        items: [],
      }));
    } catch (e) {
      console.warn('写入localStorage失败:', e);
    }
    setProgress({});
    setMoney(0);
    setItems([]);
  };

  return (
    <div style={{
      position: 'relative',
      minHeight: '100vh',
      overflow: 'hidden',
      fontFamily: "'PingFang SC', sans-serif",
      background: '#f5efe6', 
    }}>

    {/* ===== 地图 + SVG 一起缩放 ===== */}
    <div style={{
      position: 'absolute', inset: 0,
      transform: 'scale(1.1)',
      transformOrigin: 'center',
      transition: 'transform 0.3s ease',
    }}>
      <img src="/bg.png" alt="研学地图" style={{
        position: 'absolute', top: 0, left: 0,
        width: '100%', height: '100%',
        objectFit: 'cover', display: 'block',
        opacity: 0.3, 
      }} />

      {/* ===== 全屏 SVG 覆盖层：折线 + 站点（与图片同步铺满，不错位）===== */}
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
      >
        {/* ===== 水彩滤镜定义 ===== */}
        <defs>
          <filter id="watercolor" x="-30%" y="-30%" width="160%" height="160%">
            {/* 生成噪点 */}
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.08"
              numOctaves="4"
              seed="7"
              result="noise"
            />
            {/* 用噪点让线条边缘抖动、毛糙 */}
            <feDisplacementMap
              in="SourceGraphic"
              in2="noise"
              scale="0.8"
              xChannelSelector="R"
              yChannelSelector="G"
            />
            {/* 轻微模糊，模拟水彩晕开 */}
            <feGaussianBlur stdDeviation="0.15" />
          </filter>
        </defs>

        {/* 折线：交替 S 型波浪 + 水彩滤镜 */}
        {STATIONS.slice(0, -1).map((s, i) => {
          const segDone = progress[s.id]?.done;
          const next = STATIONS[i + 1];
          const dx = next.pos.x - s.pos.x;
          const dy = next.pos.y - s.pos.y;
          const len = Math.sqrt(dx * dx + dy * dy) || 1;

          // 垂直方向的单位向量
          const nx = -dy / len;
          const ny = dx / len;
          const amp = len * 0.22;              // 摆动幅度

          // 关键：奇偶段方向相反，形成连续波浪
          const dir = i % 2 === 0 ? 1 : -1;

          const c1x = s.pos.x + dx * 0.3 + nx * amp * dir;
          const c1y = s.pos.y + dy * 0.3 + ny * amp * dir;
          const c2x = s.pos.x + dx * 0.7 - nx * amp * dir;
          const c2y = s.pos.y + dy * 0.7 - ny * amp * dir;

          return (
            <path
              key={`seg-${s.id}`}
              d={`M ${s.pos.x} ${s.pos.y}
                  C ${c1x} ${c1y}, ${c2x} ${c2y}, ${next.pos.x} ${next.pos.y}`}
              fill="none"
              filter="url(#watercolor)"
              style={{
                stroke: segDone ? '#FF8B4D' : 'rgba(180,150,120,0.7)',
                strokeWidth: segDone ? 0.4 : 0.2,
                strokeLinecap: 'round',
                opacity: segDone ? 1.2 : 1,
                transition: 'stroke 0.4s ease, stroke-width 0.4s ease',
              }}
            />
          );
        })}

        {/* 站点标记 */}
        {STATIONS.map((s) => {
          const done = progress[s.id]?.done;
          const isCurrent = s.id === currentStationId;
          const locked = !done && !isCurrent;

          // 定位针尺寸：当前站/已完成稍大
          const pinW = isCurrent ? 2.3 : done ? 1.8: 1.5;   // 针的宽度
          const pinH = pinW * 1.2;                      // 针的高度
          const pinColor = done ? '#4CAF50'             // 已完成：绿色
                         : isCurrent ? '#FF8B4D'        // 当前站：橙色
                         : '#FF8B4D';                   // 未完成：橙色（可改灰）

          return (
            <g
              key={s.id}
              onClick={() => handleStationClick(s)}
              style={{ cursor: locked ? 'not-allowed' : 'pointer' }}
            >
              {/* 当前站的呼吸光圈 */}
              {isCurrent && (
                <circle cx={s.pos.x} cy={s.pos.y} r={2} fill="#FF8B4D" opacity={0.15} />
              )}

              {/* 实心定位针：针尖在 (x, y)，所以整体向上平移 pinH */}
              {/* 实心定位针：圆润水滴形，无白边 */}
              <path
                d={`M ${s.pos.x} ${s.pos.y}
                    c ${-pinW * 0.55} ${-pinH * 0.35},
                      ${-pinW * 0.55} ${-pinH},
                      ${0} ${-pinH}
                    c ${pinW * 0.55} ${0},
                      ${pinW * 0.55} ${pinH * 0.65},
                      ${0} ${pinH} Z`}
                fill={pinColor}
              />
              {/* 针中间的白色小圆孔（保留，像真实地图针） */}
              <circle
                cx={s.pos.x}
                cy={s.pos.y - pinH * 0.62}
                r={pinW * 0.2}
                fill="white"
              />
              {/* 针中间的白色小圆孔 */}
              <circle
                cx={s.pos.x}
                cy={s.pos.y - pinH * 0.62}
                r={pinW * 0.18}
                fill="white"
              />

              {/* 站名文字：针上方 */}
              <text
                x={s.pos.x} y={s.pos.y - pinH - 2}
                textAnchor="middle"
                fontSize={1.5} //站点字体大小
                fontWeight="bold"
                fill={locked ? '#9a9086' : '#5D4037'}
                style={{ paintOrder: 'stroke', stroke: 'rgba(255,255,255,0.9)', strokeWidth: 0.6}}
              >
                {s.name}
              </text>
            </g>
          );
        })}
      </svg>
      </div>
      {/* ===== 顶部浮层 ===== */}
      <div style={{
        position: 'relative', zIndex: 10,
        padding: '1.5rem 2rem',
        display: 'flex', alignItems: 'center', gap: '1rem',
        flexWrap: 'wrap',
      }}>

      {/* 标题：沉浸式研学 */}
      <h1 style={{
        fontSize: 'clamp(1.6rem, 3.5vw, 2.4rem)',
        fontWeight: '800',
        color: '#8B4513',
        margin: 0,
        display: 'flex', alignItems: 'center', gap: '0.6rem',
        whiteSpace: 'nowrap',
        textShadow: '0 0 8px rgba(255,255,255,0.95), 0 0 4px rgba(255,255,255,0.95)',
      }}>
        {/* 纯实心橙色地图图标 */}
        <svg
          width="1.5em" height="1.5em" viewBox="0 0 24 24"
          fill="#FF8B4D"
          style={{ flexShrink: 0 }}
        >
          <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/>
        </svg>
        沉浸式研学
      </h1>

        {/* 进度摘要：夹在中间，三等分，无白框，间距缩小 */}
        <div style={{
          flex: 1,
          display: 'flex',
          justifyContent: 'center',      // 整体居中，不撑满
          gap: '3.2rem',                 // ← 三个之间的间距，改小就是这里
          minWidth: '500px',
        }}>
          {[
            `💰 ${money} 大洋`,
            `🎒 道具 ${items.length}/3`,
            `📍 完成 ${doneCount}/5`,
          ].map((text, i) => (
            <span key={i} style={{
              fontSize: 'clamp(1.6rem, 2.4vw, 2.0rem)',  // 比标题小一档
              fontWeight: '700',
              color: '#5D4037',
              whiteSpace: 'nowrap',
              textShadow: '0 0 8px rgba(255,255,255,0.95), 0 0 4px rgba(255,255,255,0.95)',
            }}>
              {text}
            </span>
          ))}
        </div>

                  {/* 撤销上一站 */}
          <button
            onClick={undoLastStation}
            title="撤销上一站"
            style={{
              background: 'white',
              border: '2px solid #FF8B4D',
              color: '#FF8B4D',
              width: '3rem', height: '3rem',
              borderRadius: '0.75rem',
              fontSize: '1.4rem',
              fontWeight: '700',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
              transition: 'all 0.3s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#FFF3EA'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'white'; }}
          >
            ↶
          </button>

          {/* 重置全部进度 */}
          <button
            onClick={resetAllProgress}
            style={{
              background: 'white',
              border: '2px solid #999',
              color: '#666',
              padding: '0.75rem 1.5rem',
              borderRadius: '0.75rem',
              fontSize: '1.1rem',
              fontWeight: '600',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              whiteSpace: 'nowrap',
              boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
              transition: 'all 0.3s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#f0f0f0'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'white'; }}
          >
            <span>↺</span> 重置
          </button>


        {/* 返回首页按钮：宽度再加宽 */}
        <button
          onClick={() => navigate('/')}
          style={{
            background: 'white',
            border: '2px solid #FF8B4D',
            color: '#FF8B4D',
            padding: '0.75rem 2.8rem',    // ← 左右从 1.5rem 加到 2.2rem，更宽
            borderRadius: '0.75rem',
            fontSize: '1.3rem',
            fontWeight: '500',
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: '0.5rem',
            whiteSpace: 'nowrap',
            boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
            transition: 'all 0.3s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = '#FFF3EA';
            e.currentTarget.style.boxShadow = '0 6px 16px rgba(0,0,0,0.18)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'white';
            e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.12)';
          }}
        >
          <span>←</span> 返回首页
        </button>
      </div>
    </div>
  );
}

export default StationsPage;
