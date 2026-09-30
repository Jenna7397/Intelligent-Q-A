import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';

// 5个站点详细配置
const STATION_DETAILS = {
  1: {
    name: '上盐村',
    title: '郑正秋故居',
    icon: '🎬',
    npcIntro: '电影之父郑正秋，编导了中国第一部短故事片《难夫难妻》，又推出中国第一部有声电影《歌女红牡丹》，一生编导影片数十部，为中国早期电影奠基，被誉为"中国电影之父"。',
    task: '10道关于潮影文化的题，答对6题以上才能获得资助。',
    reward: { money: 6, item: '水布' },
    // 10道题（从知识库出）
    questions: [
      { q: '郑正秋是中国哪个领域的先驱人物？', options: ['绘画', '音乐', '电影', '建筑'], answer: 2 },
      { q: '郑正秋的祖籍地是今天的哪里？', options: ['福建厦门', '广东潮阳', '广东梅州', '福建泉州'], answer: 1 },
      { q: '郑正秋编导的中国第一部短故事片是？', options: ['《难夫难妻》', '《歌女红牡丹》', '《渔光曲》', '《十字街头》'], answer: 0 },
      { q: '郑正秋参与创办的影片公司叫什么名字？', options: ['联华影业公司', '天一影片公司', '长城画片公司', '明星影片公司'], answer: 3 },
      { q: '中国第一部有声电影《歌女红牡丹》上映于哪一年？', options: ['1925年', '1931年', '1937年', '1940年'], answer: 1 },
      { q: '郑正秋在创作中尤其擅长哪类题材？', options: ['科幻与未来', '武侠与神怪', '战争与军事', '家庭伦理与社会现实'], answer: 3 },
      { q: '郑正秋执导的《姊妹花》由哪位女演员一人分饰两角？', options: ['阮玲玉', '胡蝶', '周璇', '上官云珠'], answer: 1 },
      { q: '郑正秋被后世尊称为什么？', options: ['中国话剧之父', '中国动画之父', '中国电影之父', '中国摄影之父'], answer: 2 },
      { q: '郑正秋的故居位于潮汕的哪个村？', options: ['东盐村', '大寮村', '上盐村', '田中央'], answer: 2 },
      { q: '郑正秋的作品多关注底层民众，体现了他怎样的创作立场？', options: ['关注现实、同情民生', '追求奇幻想象', '崇尚宫廷生活', '偏爱异域风情'], answer: 0 },
    ],
  },
  2: {
    name: '东盐村',
    title: '粿品工坊',
    icon: '🥮',
    npc: '祖母',
    npcIntro: '慈祥的潮汕阿婆，正在做你最爱吃的红桃粿。',
    task: '帮祖母一起做红桃粿。做完后，祖母会送你甜粿和十个大洋作为盘缠。',
    reward: { money: 10, item: '甜粿' },
  },
  3: {
    name: '大寮村',
    title: '嵌瓷工艺社',
    icon: '🏺',
    npc: '许师傅',
    npcIntro: '嵌瓷老艺人，手艺精湛，性格豪爽。',
    task: '帮许师傅制作嵌瓷盘子。作品越精美，获得的大洋越多。完成后获赠市篮。',
    reward: { money: 3, item: '市篮' },
  },
  4: {
    name: '文化公园',
    title: '华侨名人展',
    icon: '🎖️',
    npc: '王村长',
    npcIntro: '全程陪同的王村长。',
    task: '观看蚁光炎事迹短片，了解华侨抗战历史和潮人精神。',
    reward: { money: 0, item: null },
  },
  5: {
    name: '田中央',
    title: '侨批局',
    icon: '✉️',
    npc: '批局老板',
    npcIntro: '侨批，是海外华侨寄回家乡的银信合封，一纸"批"里既有汇款、又含家书，被称为"海邦剩馥"。当年无数潮汕人正是靠这一封封侨批，维系着与家乡的血脉亲情。今天，批局老板带你走进侨批局，亲手体验一次写批、寄批的过程。',
    task: '在批局老板的指引下体验送批，然后写一封侨批寄给你想寄的人。花5大洋可以自己写，花10大洋可请写批先生代笔。',
    reward: { money: -5, item: '文创兑换券' },
  },
};

function StationDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const station = STATION_DETAILS[id];

  const [progress, setProgress] = useState({});
  const [money, setMoney] = useState(0);
  const [items, setItems] = useState([]);
  const [quizAnswers, setQuizAnswers] = useState([]);
  const [quizDone, setQuizDone] = useState(false);
  const [score, setScore] = useState(0);
  const [letterText, setLetterText] = useState('');
  const [letterSent, setLetterSent] = useState(false);
  const [completed, setCompleted] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem('qiaoxiang_progress');
    if (saved) {
      const data = JSON.parse(saved);
      setProgress(data.stations || {});
      setMoney(data.money || 0);
      setItems(data.items || []);
      if (data.stations?.[id]?.done) setCompleted(true);
    }
  }, [id]);

  if (!station) {
    return <div style={{ padding: '2rem' }}>站点不存在</div>;
  }

  const saveProgress = (newProgress, newMoney, newItems) => {
    const data = {
      stations: newProgress,
      money: newMoney,
      items: newItems,
    };
    localStorage.setItem('qiaoxiang_progress', JSON.stringify(data));
  };

  const completeStation = () => {
    const reward = station.reward;
    let newMoney = money + (reward.money || 0);
    let newItems = [...items];
    if (reward.item && !newItems.includes(reward.item)) {
      newItems.push(reward.item);
    }
    const newProgress = { ...progress, [id]: { done: true, reward: reward.item } };
    setProgress(newProgress);
    setMoney(newMoney);
    setItems(newItems);
    setCompleted(true);
    saveProgress(newProgress, newMoney, newItems);
  };

  // 答题逻辑
  const handleAnswer = (qIdx, optIdx) => {
    const newAnswers = [...quizAnswers];
    newAnswers[qIdx] = optIdx;
    setQuizAnswers(newAnswers);
  };

  const submitQuiz = () => {
    let s = 0;
    station.questions.forEach((q, i) => {
      if (quizAnswers[i] === q.answer) s++;
    });
    setScore(s);
    setQuizDone(true);
    // 答对6题得6个大洋，多对一题加1个
    const earnedMoney = s >= 6 ? Math.min(s, 10) : 0;
    setMoney(prev => prev + earnedMoney);
    const newItems = [...items];
    if (!newItems.includes('水布')) newItems.push('水布');
    const newProgress = { ...progress, [id]: { done: true, reward: '水布', score: s } };
    setProgress(newProgress);
    setItems(newItems);
    saveProgress(newProgress, money + earnedMoney, newItems);
    setCompleted(true);
  };

  // 写侨批
  const sendLetter = () => {
    if (!letterText.trim()) return;
    setLetterSent(true);
    // 花5大洋
    const newMoney = money - 5;
    setMoney(newMoney);
    const newItems = [...items];
    if (!newItems.includes('文创兑换券')) newItems.push('文创兑换券');
    const newProgress = { ...progress, [id]: { done: true, reward: '文创兑换券' } };
    setProgress(newProgress);
    setItems(newItems);
    saveProgress(newProgress, newMoney, newItems);
    setCompleted(true);
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(180deg, #FFF5EB 0%, #FFF 100%)',
      padding: '1.5rem 1rem',
      fontFamily: "'PingFang SC', sans-serif",
    }}>
      <div style={{ maxWidth: '720px', margin: '0 auto' }}>

        {/* 返回按钮 */}
        <button
          onClick={() => navigate('/stations')}
          style={{
            background: 'none',
            border: 'none',
            color: '#8B4513',
            fontSize: '1.8rem',
            cursor: 'pointer',
            marginBottom: '1rem',
            padding: 0,
          }}
        >
          ← 返回导航
        </button>

        {/* 站点标题 */}
        <div style={{
          background: 'white',
          borderRadius: '1rem',
          padding: '1.5rem',
          marginBottom: '1rem',
          boxShadow: '0 2px 8px rgba(139,69,19,0.08)',
        }}>
          {/* icon + 标题同一行 */}
          <h1 style={{
            fontSize: '2.8rem',
            fontWeight: '700',
            color: '#333',
            margin: 0,
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
            lineHeight: 1.2,
          }}>
            <span>{station.icon}</span>
            第{id}站 · {station.name}
            {/* 第5站：副标题接在同一行 */}
            {id === '5' && (
              <span style={{ fontSize: '3rem', color: '#333', fontWeight: '700' }}>
                {station.title}
              </span>
            )}
          </h1>
          {/* 第1~4站：副标题单独一行 */}
          {id !== '5' && (
            <p style={{ color: '#666', fontSize: '1.5rem', margin: '0.5rem 0 0' }}>
              {station.title}
            </p>
          )}
        </div>

        {/* NPC介绍 */}
        <div style={{
          background: '#FFF8F0',
          borderRadius: '1rem',
          padding: '1.2rem',
          marginBottom: '1rem',
          borderLeft: '4px solid #FF8B4D',
        }}>
          <p style={{ color: '#555', fontSize: '1.3rem', margin: 0, lineHeight: 1.7 }}>
            <strong style={{ color: '#8B4513' }}>介绍：</strong>
            {station.npcIntro}
          </p>
        </div>

        {/* 任务说明 */}
        <div style={{
          background: 'white',
          borderRadius: '1rem',
          padding: '1.2rem',
          marginBottom: '1rem',
        }}>
          <p style={{ color: '#555', fontSize: '1.3rem', margin: 0, lineHeight: 1.7 }}>
            <strong style={{ color: '#8B4513' }}>📋 任务：</strong>
            {station.task}
          </p>
        </div>

        {/* 互动区 */}
        {/* 第1站：答题 */}
        {id === '1' && !completed && (
          <div style={{
            background: 'white',
            borderRadius: '1rem',
            padding: '1.2rem',
            marginBottom: '1rem',
          }}>
            <div style={{ fontSize: '1.3rem', fontWeight: '700', color: '#8B4513', marginBottom: '1rem' }}>
              🎬 潮影文化十问
            </div>
            {!quizDone ? (
              <>
                {station.questions.map((q, qi) => (
                  <div key={qi} style={{ marginBottom: '1rem' }}>
                    <div style={{ fontSize: '1.3rem', fontWeight: '600', marginBottom: '0.6rem' }}>
                      {qi + 1}. {q.q}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                      {q.options.map((opt, oi) => (
                        <button
                          key={oi}
                          onClick={() => handleAnswer(qi, oi)}
                          style={{
                            textAlign: 'left',
                            padding: '0.8rem 1rem',
                            borderRadius: '0.5rem',
                            border: quizAnswers[qi] === oi ? '2px solid #FF8B4D' : '1px solid #ddd',
                            background: quizAnswers[qi] === oi ? '#FFF0E0' : 'white',
                            fontSize: '1.3rem',
                            cursor: 'pointer',
                          }}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                ))}
                <button
                  onClick={submitQuiz}
                  disabled={quizAnswers.filter(a => a !== undefined).length < station.questions.length}
                  style={{
                    width: '100%',
                    background: '#FF8B4D',
                    color: 'white',
                    border: 'none',
                    padding: '0.9rem',
                    borderRadius: '0.5rem',
                    fontSize: '1.3rem',
                    fontWeight: '600',
                    cursor: 'pointer',
                    marginTop: '0.5rem',
                  }}
                >
                  交卷
                </button>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: '1rem' }}>
                <div style={{ fontSize: '2rem' }}>{score >= 6 ? '🎉' : '😅'}</div>
                <div style={{ fontSize: '1.1rem', fontWeight: '700', color: '#333', marginTop: '0.5rem' }}>
                  答对 {score}/10 题
                </div>
                <div style={{ color: '#666', fontSize: '0.9rem', marginTop: '0.3rem' }}>
                  {score >= 6 ? `获得${Math.min(score, 10)}个大洋和水布！` : '答对不足6题，再去潮影馆看看吧'}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 第5站：写侨批 */}
        {id === '5' && !completed && (
          <div style={{
            background: 'white',
            borderRadius: '1rem',
            padding: '1.2rem',
            marginBottom: '1rem',
          }}>
            <div style={{ fontSize: '1.3rem', fontWeight: '700', color: '#8B4513', marginBottom: '0.5rem' }}>
              ✉️ 写一封侨批
            </div>
            <textarea
              value={letterText}
              onChange={(e) => setLetterText(e.target.value)}
              placeholder="写一封给亲人的侨批，告诉他们你在南洋的近况..."
              style={{
                width: '100%',
                minHeight: '120px',
                padding: '1rem',
                borderRadius: '0.5rem',
                border: '1px solid #ddd',
                fontSize: '1.3rem',
                resize: 'vertical',
                boxSizing: 'border-box',
              }}
            />
            <button
              onClick={sendLetter}
              disabled={!letterText.trim() || letterSent}
              style={{
                width: '100%',
                background: '#FF8B4D',
                color: 'white',
                border: 'none',
                padding: '0.9rem',
                borderRadius: '0.5rem',
                fontSize: '1rem',
                fontWeight: '600',
                cursor: 'pointer',
                marginTop: '0.5rem',
              }}
            >
              {letterSent ? '✅ 侨批已寄出' : '花5大洋寄出侨批'}
            </button>
          </div>
        )}

        {/* 其他站：完成按钮 */}
        {!['1', '5'].includes(id) && !completed && (
          <button
            onClick={completeStation}
            style={{
              width: '100%',
              background: '#FF8B4D',
              color: 'white',
              border: 'none',
              padding: '1rem',
              borderRadius: '0.5rem',
              fontSize: '1rem',
              fontWeight: '600',
              cursor: 'pointer',
              marginBottom: '1rem',
            }}
          >
            ✓ 我已完成本站任务
          </button>
        )}

        {/* 完成提示 */}
        {completed && (
          <div style={{
            background: '#E8F5E9',
            borderRadius: '1rem',
            padding: '1.5rem',
            textAlign: 'center',
            marginBottom: '1rem',
          }}>
            {/* ✅ 和文字同一行 */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem',
              fontSize: '1.5rem',
              fontWeight: '700',
              color: '#2E7D32',
            }}>
              <span>✅</span>
              本任务已完成
            </div>
            {station.reward.item && (
              <div style={{ color: '#555', fontSize: '1.3rem', marginTop: '0.6rem' }}>
                获得：{station.reward.item}
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}

export default StationDetailPage;
