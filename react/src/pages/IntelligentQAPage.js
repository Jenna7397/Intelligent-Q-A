import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

import 'tailwindcss/tailwind.css';

const IntelligentQA = () => {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [speechProgress, setSpeechProgress] = useState(0);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isTtsLoading, setIsTtsLoading] = useState(false);
  const inputRef = useRef(null);
  const contentRef = useRef(null);
  const audioRef = useRef(null);
  const ttsFailCountRef = useRef(0);
  const abortRef = useRef(null);
  const sentenceQueueRef = useRef([]);
  const isPlayingRef = useRef(false);
  const fullContentRef = useRef('');
  const titleDoneRef = useRef(false);
  const lastSentencePosRef = useRef(0);

  const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8001';
  const TTS_API_URL = process.env.REACT_APP_TTS_URL || 'http://localhost:8002';

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      const controller = abortRef.current;
      if (controller) controller.abort();
    };
  }, []);

  // 滚动到底部
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [content]);

  // TTS 播放队列：串行播放句子
  const playSentence = async (text) => {
    if (!text || !text.trim()) return;
    setIsTtsLoading(true);
    try {
      const resp = await axios.post(`${TTS_API_URL}/api/tts`, { text }, {
        headers: { 'Content-Type': 'application/json' },
        timeout: 60000
      });
      if (!resp.data.success || !resp.data.audio_base64) {
        ttsFailCountRef.current++;
        console.warn('TTS失败:', resp.data.error);
        if (ttsFailCountRef.current >= 3) {
          setErrorMsg('语音服务连续失败，已自动停止语音讲解（文字内容不受影响）');
          sentenceQueueRef.current = [];
          isPlayingRef.current = false;
          setIsTtsLoading(false);
          setIsSpeaking(false);
          return;
        }
        return;
      }
      if (audioRef.current) { audioRef.current.pause(); }
      const audio = new Audio(`data:audio/mp3;base64,${resp.data.audio_base64}`);
      audioRef.current = audio;
      setIsSpeaking(true);
      setSpeechProgress(0);

      ttsFailCountRef.current = 0;
      audio.ontimeupdate = () => {
        if (audio.duration) setSpeechProgress(Math.round((audio.currentTime / audio.duration) * 100));
      };
      audio.onended = () => {
        setIsSpeaking(false);
        setSpeechProgress(0);
        isPlayingRef.current = false;
        playNextFromQueue();
      };
      audio.onerror = () => {
        setIsSpeaking(false);
        setSpeechProgress(0);
        isPlayingRef.current = false;
        playNextFromQueue();
      };
      await audio.play();
    } catch (e) {
      ttsFailCountRef.current++;
      console.warn('TTS播放失败:', e.message);
      if (ttsFailCountRef.current >= 3) {
        setErrorMsg('语音服务连续失败，已自动停止语音讲解（文字内容不受影响）');
        sentenceQueueRef.current = [];
        isPlayingRef.current = false;
        setIsTtsLoading(false);
        setIsSpeaking(false);
        return;
      }
      isPlayingRef.current = false;
      playNextFromQueue();
    } finally {
      setIsTtsLoading(false);
    }
  };

  const playNextFromQueue = () => {
    if (isPlayingRef.current) return;
    const next = sentenceQueueRef.current.shift();
    if (next) {
      isPlayingRef.current = true;
      playSentence(next);
    }
  };

  const stopSpeaking = () => {
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    sentenceQueueRef.current = [];
    isPlayingRef.current = false;
    setIsSpeaking(false);
    setSpeechProgress(0);
  };

  // SSE 流式获取故事
  const fetchStoryStream = async () => {
    if (!query.trim()) return setErrorMsg('请输入有效问题');
    setIsLoading(true);
    setIsStreaming(true);
    setErrorMsg('');
    setTitle('');
    setContent('');
    fullContentRef.current = '';
    titleDoneRef.current = false;
    lastSentencePosRef.current = 0;
    ttsFailCountRef.current = 0;
    sentenceQueueRef.current = [];
    stopSpeaking();

    try {
      const resp = await fetch(`${API_BASE_URL}/get_story_stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim() })
      });

      if (!resp.ok || !resp.body) throw new Error('流式请求失败');

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const evt of events) {
          const line = evt.trim();
          if (!line.startsWith('data:')) continue;
          const data = line.slice(5).trim();
          if (data === '[DONE]') break;
          try {
            const parsed = JSON.parse(data);
            if (parsed.error) {
              setErrorMsg(parsed.error);
              continue;
            }
            const delta = parsed.delta || '';
            if (!delta) continue;

            if (!titleDoneRef.current) {
              const newlineIdx = delta.indexOf('\n');
              if (newlineIdx >= 0) {
                setTitle(prev => prev + delta.slice(0, newlineIdx));
                titleDoneRef.current = true;
                const rest = delta.slice(newlineIdx + 1);
                if (rest) {
                  setContent(prev => prev + rest);
                  fullContentRef.current += rest;
                  enqueueSentences();
                }
              } else {
                setTitle(prev => prev + delta);
              }
            } else {
              setContent(prev => prev + delta);
              fullContentRef.current += delta;
              enqueueSentences();
            }
          } catch (e) { /* 忽略解析错误 */ }
        }
      }
    } catch (e) {
      let msg = '流式请求失败';
      if (e.message.includes('Network Error')) msg = '网络连接失败（请确认后端已启动）';
      setErrorMsg(msg);
      console.error(e);
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
      const tail = fullContentRef.current.slice(lastSentencePosRef.current).trim();
      if (tail) {
        sentenceQueueRef.current.push(tail);
      }
      playNextFromQueue();
    }
  };

  // 按句号/问号/感叹号切句入队（只扫新增部分）
  const enqueueSentences = () => {
    const text = fullContentRef.current;
    const hardStop = /[。！？；…]/g;
    hardStop.lastIndex = lastSentencePosRef.current;
    let match;
    let progressed = false;
    while ((match = hardStop.exec(text)) !== null) {
      const endPos = match.index + 1;
      const sentence = text.slice(lastSentencePosRef.current, endPos).trim();
      if (sentence) sentenceQueueRef.current.push(sentence);
      lastSentencePosRef.current = endPos;
      progressed = true;
    }
    const pending = text.slice(lastSentencePosRef.current);
    if (pending.length >= 25) {
      const commaIdx = pending.search(/[，、]/);
      if (commaIdx > 10) {
        const cutPos = lastSentencePosRef.current + commaIdx + 1;
        const sentence = text.slice(lastSentencePosRef.current, cutPos).trim();
        if (sentence) sentenceQueueRef.current.push(sentence);
        lastSentencePosRef.current = cutPos;
        progressed = true;
      }
    }
    if (progressed) playNextFromQueue();
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-orange-100 to-white p-4 md:p-8">
      <header className="mb-8 container mx-auto">
        <div className="container mx-auto flex flex-col md:flex-row justify-between items-center">
          <h1 className="text-[clamp(1.2rem,4vw,2.5rem)] font-bold text-orange-800 mb-4 md:mb-0 flex items-center">
            <i className="fa fa-book-open text-orange-600 mr-4"></i>
            侨乡故事智能问答
          </h1>
          <button
            onClick={() => navigate('/')}
            className="bg-white border-2 border-orange-600 text-orange-600 px-6 py-3 rounded-lg font-medium transition-all duration-300 hover:bg-orange-50 hover:shadow-md flex items-center"
          >
            <i className="fa fa-arrow-left mr-3"></i> 返回首页
          </button>
        </div>
      </header>

      <main className="container mx-auto grid grid-cols-1 lg:grid-cols-12 gap-10">
        {/* 左侧：讲解员卡片 —— 固定高度 */}
        <div className="lg:col-span-4 order-2 lg:order-1">
          <div className="bg-white rounded-3xl shadow-2xl overflow-hidden h-[930px] flex flex-col">
            <div className="relative shrink-0">
              <img
                src="/people.png"
                alt="侨乡文化讲解员啊顺"
                className="w-full h-100 object-cover rounded-t-3xl"
                onError={(e) => e.target.src = "https://source.unsplash.com/random/600x400?people,history"}
              />
              {isSpeaking && (
                <div className="absolute right-6 bottom-6 bg-orange-700 text-white rounded-full p-4 shadow-3xl">
                  <i className="fa fa-volume-up text-2xl animate-pulse"></i>
                </div>
              )}
            </div>
            <div className="p-8 flex-1 overflow-y-auto">
              <h3 className="text-3xl font-bold text-orange-800 mb-4">侨乡文化智能讲解员</h3>
              <p className="text-2xl text-gray-700 leading-7 mb-6">
                专注为您呈现侨乡历史脉络、侨胞奋斗足迹、侨批文化密码与侨宅建筑美学，直接提问即可开启探索～
              </p>

              {title && (
                <div className="mt-8 bg-orange-50 rounded-3xl p-6">
                  <h4 className="text-xl font-semibold text-orange-600 mb-3 flex items-center gap-4">
                    <div className="w-8 h-8 bg-orange-600 rounded-full animate-bounce"></div>
                    当前正在讲解：{title}
                  </h4>
                  <div className="mt-4">
                    <div className="w-full bg-orange-100 rounded-full h-3">
                      <div className="bg-orange-600 h-3 rounded-full transition-all duration-300" style={{ width: `${speechProgress}%` }}></div>
                    </div>
                    <div className="text-base text-gray-600 mt-2 flex justify-between">
                      <span>{Math.round(speechProgress)}%</span>
                      <span>{isTtsLoading ? '语音合成中...' : isSpeaking ? '正在播放' : '就绪'}</span>
                    </div>
                  </div>
                  <button
                    onClick={stopSpeaking}
                    disabled={!isSpeaking && !isTtsLoading}
                    className="mt-5 bg-orange-100 text-orange-600 px-6 py-3 rounded-3xl hover:bg-orange-200 disabled:opacity-50 text-lg"
                  >
                    <i className="fa fa-stop-circle mr-3"></i> 停止讲解
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 右侧：提问 + 内容 —— 固定高度，与左侧等高 */}
        <div className="lg:col-span-8 order-1 lg:order-2 flex flex-col h-[930px]">
          {/* 输入卡片：固定高度 */}
          <div className="mb-8 bg-white rounded-3xl shadow-2xl p-8 shrink-0">
            <div className="flex flex-col md:flex-row gap-6">
              <input
                ref={inputRef}
                type="text"
                placeholder="请提问（例如：成田镇的侨乡故事）"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !isLoading && fetchStoryStream()}
                className="flex-grow px-6 py-5 rounded-3xl border-2 border-gray-200 focus:border-orange-600 focus:ring-2 focus:ring-orange-200 outline-none text-xl"
              />
              <button
                onClick={fetchStoryStream}
                disabled={isLoading || !query.trim()}
                className="bg-orange-600 hover:bg-orange-700 text-white font-semibold px-8 py-4 rounded-3xl shadow-md hover:shadow-lg transition-all duration-300 disabled:opacity-70 text-xl"
              >
                {isLoading ? '生成中...' : '获取故事'}
              </button>
            </div>
          </div>

          {/* 内容卡片：占满剩余高度，内部滚动 */}
          <div className="bg-white rounded-3xl shadow-2xl p-8 flex-1 overflow-hidden flex flex-col">
            {errorMsg && (
              <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 shrink-0">
                {errorMsg}
              </div>
            )}
            {title || content ? (
              <>
                {title && (
                  <h3 className="text-2xl font-bold text-gray-900 mb-6 pb-3 border-b-2 border-orange-100 shrink-0">
                    {title}
                    {isStreaming && <span className="inline-block w-1 h-5 bg-orange-600 ml-2 animate-pulse align-middle"></span>}
                  </h3>
                )}
                <p
                  ref={contentRef}
                  className="text-2xl text-gray-700 leading-8 whitespace-pre-wrap overflow-y-auto flex-1"
                >
                  {content}
                  {isStreaming && <span className="inline-block w-1 h-5 bg-orange-600 ml-1 animate-pulse"></span>}
                </p>
              </>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center flex-1">
                <div className="w-24 h-24 mb-6 text-gray-300">
                  <i className="fa fa-book-open text-7xl"></i>
                </div>
                <h3 className="text-2xl font-medium text-gray-500 mb-4">侨乡故事智能问答</h3>
                <p className="text-gray-500 max-w-md text-lg">
                  请输入问题，获取关于侨乡、侨胞、侨批、侨宅的故事，支持流式输出与语音同步讲解
                </p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default IntelligentQA;