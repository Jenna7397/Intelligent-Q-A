# Intelligent Q&A —— 潮汕侨乡文化智能问答与路线规划系统

一个基于 RAG（检索增强生成）的潮汕侨乡文化问答平台，同时提供侨宅主题游览路线规划功能。后端为 FastAPI 多服务架构，前端为 React 单页应用。

## 功能特性

- **智能问答**：基于本地知识库（潮汕侨宅、华侨历史等资料）的检索增强问答，回答有据可依
- **路线规划**：根据兴趣点自动生成侨乡文化游览路线，覆盖潮汕地区多个侨宅遗址
- **侨乡故事**：按主题呈现华侨家族故事与文化解读
- **语音合成（TTS）**：为问答与故事内容提供语音播报

## 技术栈

| 端 | 技术 |
|---|---|
| 后端 | Python · FastAPI · Uvicorn |
| 知识库 | RAG（FastEmbed + ONNX Runtime）· Chroma 向量库 |
| 前端 | React 19 · React Router 7 · Axios |
| 其他 | python-dotenv · requests |

## 项目结构

```
QA/
├── fastapi/                  # 后端服务
│   ├── main.py               # 一键启动全部服务
│   ├── route_generator.py    # 路线生成服务（端口 8000）
│   ├── qiaoxiang_story.py    # 侨乡故事服务（端口 8001）
│   ├── tts.py                # 语音合成服务（端口 8002）
│   ├── kb_build.py           # 知识库构建脚本
│   ├── kb_retriever.py       # 知识检索模块
│   ├── eval_rag.py           # RAG 效果评估
│   ├── db.py                 # 数据库访问
│   └── requirements.txt
├── react/                    # 前端应用
│   ├── src/pages/            # 页面组件
│   │   ├── HomePage.js
│   │   ├── IntelligentQAPage.js   # 智能问答页
│   │   ├── RoutePlannerPage.js    # 路线规划页
│   │   ├── StationsPage.js        # 站点列表页
│   │   └── StationDetailPage.js   # 站点详情页
│   └── public/
└── .gitignore
```

## 快速开始

### 1. 启动后端

```bash
cd fastapi
pip install -r requirements.txt

# 方式一：一键启动全部服务
python main.py

# 方式二：分别启动
uvicorn route_generator:app --port 8000
uvicorn qiaoxiang_story:app --port 8001
uvicorn tts:app --port 8002
```

> 首次运行前需要先构建知识库：`python kb_build.py`（知识库原始数据位于本地 `kb_data/` 目录）。

### 2. 启动前端

```bash
cd react
npm install
npm start
```

浏览器访问 `http://localhost:3000`。

## 端口一览

| 服务 | 端口 |
|---|---|
| 路线生成 | 8000 |
| 侨乡故事 | 8001 |
| 语音合成 | 8002 |
| 前端 | 3000 |

## 说明

- 知识库原始资料（`kb_data/`）、向量库（`kb_store/`）属于本地数据，已通过 `.gitignore` 排除，不随代码上传
- 环境变量配置请参考 `.env`（含密钥，勿提交）
