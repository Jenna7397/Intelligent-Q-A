import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const BACKEND_API_URL = process.env.REACT_APP_BACKEND_API_URL || 'http://localhost:8000';

// markdown渲染：把简单markdown转成带样式的HTML
function formatText(text) {
  if (!text) return '';
  let t = text;
  // 去掉代码块
  t = t.replace(/```json/g, '').replace(/```/g, '');
  // 加粗 **text**
  t = t.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
  // 标题 # / ## / ###
  t = t.replace(/^### (.*?)$/gm, '<div style="font-size:1rem;font-weight:700;color:#ff7a45;margin:0.5rem 0">$1</div>');
  t = t.replace(/^## (.*?)$/gm, '<div style="font-size:1.1rem;font-weight:700;color:#ff7a45;margin:0.5rem 0">$1</div>');
  t = t.replace(/^# (.*?)$/gm, '<div style="font-size:1.2rem;font-weight:700;color:#333;margin:0.5rem 0">$1</div>');
  // 列表
  t = t.replace(/^[-•] (.*?)$/gm, '<div style="padding-left:0.5rem">· $1</div>');
  // 换行
  t = t.replace(/\n/g, '<br/>');
  return t;
}

const RoutePlannerPage = () => {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState([]);
  const [currentConvId, setCurrentConvId] = useState(() => {
      const saved = localStorage.getItem('qiaoxiang_conv_id');
      if (!saved) return null;
      const n = parseInt(saved, 10);
      return (Number.isInteger(n) && n > 0) ? n : null;
  });
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const bottomRef = useRef(null);

  const loadConversations = async () => {
    try {
      const res = await axios.get(`${BACKEND_API_URL}/api/agent/conversations`);
      setConversations(res.data || []);
    } catch (e) { console.error(e); }
  };

  const loadConversation = async (convId) => {
    try {
      const res = await axios.get(`${BACKEND_API_URL}/api/agent/conversations/${convId}/messages`);
      setMessages(res.data.messages || []);
      setCurrentConvId(convId);
    } catch (e) { console.error(e); }
  };

  const newConversation = () => {
      setCurrentConvId(null);
      setMessages([]);
      localStorage.removeItem('qiaoxiang_conv_id');
  };

  const deleteConversation = async (e, convId) => {
    e.stopPropagation();
    try {
      await axios.delete(`${BACKEND_API_URL}/api/agent/conversations/${convId}`);
      loadConversations();
      if (currentConvId === convId) newConversation();
    } catch (e) { console.error(e); }
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg = { role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    // 先加一个空的assistant消息，流式填充
    setMessages(prev => [...prev, { role: 'assistant', content: '', streaming: true }]);

    try {
      const resp = await fetch(`${BACKEND_API_URL}/api/agent_route_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_query: input, conversation_id: currentConvId }),
      });

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'meta') {
                if (data.conversation_id && data.conversation_id > 0) {
                    setCurrentConvId(data.conversation_id);
                }
                loadConversations();
            } else if (data.type === 'step' || data.type === 'tool') {
              setMessages(prev => {
                const copy = [...prev];
                copy[copy.length - 1] = { ...copy[copy.length - 1], tool: data.text };
                return copy;
              });
            } else if (data.type === 'chunk') {
              fullText += data.text;
              setMessages(prev => {
                const copy = [...prev];
                copy[copy.length - 1] = { ...copy[copy.length - 1], content: fullText };
                return copy;
              });
            }
          } catch (e) {}
        }
      }
      // 标记streaming结束
      setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = { ...copy[copy.length - 1], streaming: false };
        return copy;
      });
    } catch (e) {
      setMessages(prev => {
        const copy = [...prev];
        copy[copy.length - 1] = { role: 'assistant', content: '请求失败，请检查后端是否启动' };
        return copy;
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadConversations(); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);
  useEffect(() => {
    if (currentConvId && currentConvId > 0) {
        localStorage.setItem('qiaoxiang_conv_id', String(currentConvId));
    }
}, [currentConvId]);

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: "'PingFang SC', sans-serif", background: '#f5f5f5' }}>

      {/* 左侧边栏 */}
      {sidebarOpen && (
        <div style={{
          width: '260px',
          background: '#2d2d2d',
          color: '#fff',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
        }}>
          {/* 返回首页 */}
          <div style={{ padding: '1rem', borderBottom: '1px solid #444' }}>
            <button
              onClick={() => navigate('/')}
              style={{
                width: '100%',
                background: 'transparent',
                color: '#aaa',
                border: '1px solid #555',
                padding: '0.6rem',
                borderRadius: '0.5rem',
                cursor: 'pointer',
                fontSize: '0.9rem',
              }}
            >
              ← 返回首页
            </button>
          </div>
          <div style={{ padding: '1rem' }}>
            <button
              onClick={newConversation}
              style={{
                width: '100%',
                background: '#ff7a45',
                color: 'white',
                border: 'none',
                padding: '0.75rem',
                borderRadius: '0.5rem',
                cursor: 'pointer',
                fontWeight: '600',
              }}
            >
              + 新对话
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '0 0.5rem' }}>
            {conversations.map(c => (
              <div
                key={c.id}
                onClick={() => loadConversation(c.id)}
                style={{
                  padding: '0.75rem',
                  marginBottom: '0.25rem',
                  borderRadius: '0.5rem',
                  cursor: 'pointer',
                  background: currentConvId === c.id ? '#444' : 'transparent',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ fontSize: '0.85rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {c.title}
                </span>
                <span
                  onClick={(e) => deleteConversation(e, c.id)}
                  style={{ color: '#888', cursor: 'pointer', fontSize: '0.8rem', marginLeft: '0.5rem' }}
                >
                  ✕
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 主区域 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* 顶栏 */}
        <div style={{
          background: '#ff7a45',
          color: 'white',
          padding: '1rem 1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
        }}>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{ background: 'none', border: 'none', color: 'white', fontSize: '1.2rem', cursor: 'pointer' }}
          >
            ☰
          </button>
          <h1 style={{ margin: 0, fontSize: '1.2rem' }}>🗺️ 鮀城慢游</h1>
        </div>

        {/* 消息列表 */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', color: '#999', marginTop: '15%' }}>
              <div style={{ fontSize: '3rem' }}>🗺️</div>
              <p style={{ fontSize: '1.1rem', color: '#666' }}>告诉我你的汕头之旅</p>
              <p style={{ fontSize: '0.9rem', marginTop: '0.5rem' }}>
                写下你的探索主题、同行人数、游玩时间，我来为你规划路线
              </p>
              <p style={{ fontSize: '0.8rem', color: '#bbb', marginTop: '1rem' }}>
                例如：我和2个朋友周末来汕头玩1天，喜欢美食和历史
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} style={{
              maxWidth: '700px',
              margin: '0 auto 1rem',
              display: 'flex',
              justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
            }}>
              <div style={{
                background: m.role === 'user' ? '#ff7a45' : 'white',
                color: m.role === 'user' ? 'white' : '#333',
                padding: '1rem 1.25rem',
                borderRadius: '1rem',
                maxWidth: '85%',
                lineHeight: '1.7',
                boxShadow: '0 2px 4px rgba(0,0,0,0.08)',
              }}>
                <div dangerouslySetInnerHTML={{ __html: formatText(m.content) }} />
                {m.tool && !m.content && (
                  <div style={{ fontSize: '0.85rem', color: '#ff7a45' }}>{m.tool}</div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div style={{ textAlign: 'center', color: '#999' }}>Agent思考中...</div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* 输入框 */}
        <div style={{
          padding: '1rem',
          background: 'white',
          borderTop: '1px solid #eee',
        }}>
          <div style={{ maxWidth: '700px', margin: '0 auto', display: 'flex', gap: '0.75rem' }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
              placeholder="写下探索主题、同行人数、游玩时间..."
              style={{
                flex: 1,
                padding: '0.85rem 1rem',
                borderRadius: '0.75rem',
                border: '1px solid #ddd',
                fontSize: '0.95rem',
              }}
            />
            <button
              onClick={sendMessage}
              disabled={loading}
              style={{
                background: '#ff7a45',
                color: 'white',
                border: 'none',
                padding: '0.85rem 1.5rem',
                borderRadius: '0.75rem',
                cursor: 'pointer',
                fontWeight: '600',
              }}
            >
              发送
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RoutePlannerPage;
