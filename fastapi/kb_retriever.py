# -*- coding: utf-8 -*-
"""
侨乡知识库检索模块 (ChromaDB 版)
供 FastAPI 接口调用：search_kb(query, top_k, type_filter)
知识库未构建或依赖缺失时自动降级返回 []，不影响原有接口运行。
"""
import os
import re
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

STORE_DIR = Path(os.getenv("CHROMA_DIR", str(Path(__file__).resolve().parent.parent / "kb_store")))
CHROMA_DB_PATH = STORE_DIR / "chroma_db"
COLLECTION_NAME = "chaoshan_knowledge"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

_model = None
_collection = None
_load_error = None
_bm25 = None  # BM25 索引缓存：{"index", "ids", "texts", "metas"}

RRF_K = 60  # RRF 融合常数：score = Σ 1/(RRF_K + rank)

# ===== 侨批长标题 → 短实体名（数据治理：name_short 字段）=====
_REM_TAIL = ["侨批局", "批局", "回批", "批封", "批信", "家书", "银信", "侨批", "档案", "故事"]
_REM_BLACK = ["汇路", "工会", "制度", "困厄", "传奇", "文化", "情感", "寄回", "第一封",
              "活体", "代写", "递送", "艺术", "商业", "风雨", "历程", "创举", "博物馆",
              "抗战", "技术", "公约", "惯例", "结汇", "专用章", "足下", "赎回"]


def extract_remittance_short(name: str) -> str:
    """从侨批长标题提取短实体名（主体人名/机构名）；提取不可靠返回空串。"""
    if not name:
        return ""
    n = name.strip()
    # 0) 去括号及内容 + 日期/年份/世纪（必须先于 "-" 处理）
    n = re.sub(r"[（(][^）)]*[）)]", "", n)
    n = re.sub(r"\d{4}年\d{1,2}月\d{1,2}日", "", n)
    n = re.sub(r"\d{4}年", "", n)
    n = re.sub(r"\d{4}-\d{2,4}", "", n)
    n = re.sub(r"\d{1,2}世纪\w{2,4}", "", n)
    n = re.sub(r"\d{1,2}年代", "", n)
    # 1) 分隔符截断："XX —— 描述" / "XX：描述"
    for sep in [" —— ", "——", "：", ":"]:
        if sep in n:
            n = n.split(sep)[0].strip()
    # 2) "-" 分隔取第一段
    if "-" in n:
        n = n.split("-")[0].strip()
    # 3) "寄给"归一，致/寄/给 截断（排除"寄回"，后接 ≤12 字才截）
    n = n.replace("寄给", "寄")
    m = re.search(r"^(.*?)(?:致|寄(?!回)|给)(?=[^，。；]{0,12}$)", n)
    if m and m.group(1).strip():
        n = m.group(1).strip()
    # 4) 循环去尾部词
    changed = True
    while changed:
        changed = False
        for t in _REM_TAIL:
            if n.endswith(t) and len(n) > len(t):
                n = n[:-len(t)].strip()
                changed = True
    # 5) 去尾部"的"；含"的"且"的"前 2~7 字 → 取"的"前
    if n.endswith("的"):
        n = n[:-1].strip()
    if "的" in n:
        before = n.split("的", 1)[0].strip()
        if 2 <= len(before) <= 7:
            n = before
    n = n.strip(" ；;，,、·")
    # 6) 黑名单 / 长度过滤
    if any(b in n for b in _REM_BLACK):
        return ""
    if not n or len(n) > 8:
        return ""
    return n


def tokenize_cjk(text: str) -> list:
    """中文按单字切分，英文/数字按词切分（不引入 jieba，覆盖实体名精确召回）"""
    import re
    return re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", text.lower())


def _get_bm25_index():
    """懒加载 BM25 索引（从 collection 全量构建，复用缓存）"""
    global _bm25
    if _bm25 is not None:
        return _bm25
    model, collection = _get_components()
    if collection is None:
        return None
    try:
        from rank_bm25 import BM25Okapi
        # 分页取全量（chromadb get 默认有 limit）
        all_ids, all_docs, all_metas = [], [], []
        offset = 0
        batch = 500
        while True:
            data = collection.get(include=["documents", "metadatas"],
                                  limit=batch, offset=offset)
            ids = data.get("ids") or []
            if not ids:
                break
            all_ids += ids
            all_docs += data.get("documents") or []
            all_metas += data.get("metadatas") or []
            offset += batch
            if len(ids) < batch:
                break
        tokenized = [tokenize_cjk(d or "") for d in all_docs]
        _bm25 = {
            "index": BM25Okapi(tokenized),
            "ids": all_ids,
            "texts": all_docs,
            "metas": all_metas,
        }
        print(f"[kb_retriever] BM25 索引构建完成：{len(all_ids)} 条")
        return _bm25
    except Exception as e:
        print(f"[kb_retriever] BM25 索引构建失败（不可用）：{e}")
        return None


def _get_components():
    """懒加载 embedding 模型与 ChromaDB collection"""
    global _model, _collection, _load_error
    if _model is not None and _collection is not None:
        return _model, _collection
    if _load_error is not None:
        return None, None
    try:
        if not CHROMA_DB_PATH.exists():
            _load_error = f"知识库不存在（{CHROMA_DB_PATH}），请先运行 python kb_build.py"
            print(f"[kb_retriever] {_load_error}")
            return None, None

        from fastembed import TextEmbedding
        import chromadb

        _model = TextEmbedding(model_name=EMBEDDING_MODEL)
        client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
        _collection = client.get_collection(COLLECTION_NAME)
        return _model, _collection
    except Exception as e:
        _load_error = str(e)
        print(f"[kb_retriever] 知识库加载失败，降级为无检索模式：{e}")
        return None, None


def search_kb(query: str, top_k: int = 5, type_filter: str = None,
              candidates: int = 20) -> list:
    """
    混合检索（向量 + BM25 + RRF 融合）。
    返回 [{text, type, name, score, full_context}]；不可用时返回 []。
    candidates: 每路召回候选池大小（RRF 融合前各取前 candidates 名）。
    score: RRF 融合分数（非相似度），数值仅用于排序/展示。
    """
    model, collection = _get_components()
    if model is None or collection is None:
        return []
    try:
        query_vector = list(model.embed([query]))[0].tolist()
        where = {"type": type_filter} if type_filter else None

        # ===== 路 1：向量检索（放大到 candidates）=====
        vec = collection.query(
            query_embeddings=[query_vector],
            n_results=candidates,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # ===== 路 2：BM25 关键词检索 =====
        bm = _get_bm25_index()
        bm_ranks = {}  # id -> rank(1-based)
        if bm is not None:
            tokens = tokenize_cjk(query)
            if tokens:
                scores = bm["index"].get_scores(tokens)
                order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
                picked = 0
                for idx in order:
                    if type_filter and bm["metas"][idx].get("type") != type_filter:
                        continue
                    bm_ranks[bm["ids"][idx]] = len(bm_ranks) + 1
                    picked += 1
                    if picked >= candidates:
                        break

        # ===== RRF 融合 =====
        from collections import defaultdict
        rrf = defaultdict(float)
        vec_ids = vec["ids"][0]
        for i, doc_id in enumerate(vec_ids):
            rrf[doc_id] += 1.0 / (RRF_K + i + 1)
        for doc_id, rank in bm_ranks.items():
            rrf[doc_id] += 1.0 / (RRF_K + rank)

        top_ids = sorted(rrf, key=rrf.get, reverse=True)[:top_k]

        # 组装返回（从 BM25 索引取全量元数据）
        # name 优先返回 name_short（侨批短实体名，如"林金珍"）；无则回退完整 name/section
        out = []
        if bm is not None:
            id_meta = {i: (t, m) for i, t, m in zip(bm["ids"], bm["texts"], bm["metas"])}
            for doc_id in top_ids:
                text, meta = id_meta[doc_id]
                out.append({
                    "text": text,
                    "type": meta.get("type", ""),
                    "name": meta.get("name_short") or meta.get("name", meta.get("section", "")),
                    "score": round(rrf[doc_id], 4),
                    "full_context": meta.get("full_context", ""),
                })
        else:
            # BM25 不可用时回退纯向量（保持可用，score 仍为相似度）
            # name 同样优先 name_short，与 BM25 分支口径一致
            id_meta = {}
            for i in range(len(vec_ids)):
                id_meta[vec_ids[i]] = (vec["documents"][0][i], vec["metadatas"][0][i])
            for doc_id in top_ids:
                if doc_id not in id_meta:
                    continue
                text, meta = id_meta[doc_id]
                out.append({
                    "text": text,
                    "type": meta.get("type", ""),
                    "name": meta.get("name_short") or meta.get("name", meta.get("section", "")),
                    "score": round(rrf[doc_id], 4),
                    "full_context": meta.get("full_context", ""),
                })
        return out
    except Exception as e:
        print(f"[kb_retriever] 检索失败：{e}")
        return []


def format_context(results: list, use_full: bool = True) -> str:
    """
    把检索结果拼成给大模型的上下文文本。
    use_full=True 时优先用 full_context（完整原文），否则只用切片。
    """
    if not results:
        return ""
    lines = []
    seen = set()
    for i, r in enumerate(results, 1):
        ctx = r["full_context"] if use_full and r.get("full_context") else r["text"]
        # 去重（同一人物的多切片可能 full_context 相同）
        if ctx in seen:
            continue
        seen.add(ctx)
        lines.append(f"[资料{i}·{r['type']}·{r['name']}]\n{ctx}")
    return "\n\n".join(lines)


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "李嘉诚为家乡做了什么"
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    res = search_kb(q, k)
    if not res:
        print("未检索到结果，或知识库未构建（请先运行 python kb_build.py）")
    for r in res:
        print(f"\n[{r['type']} | {r['name']} | score={r['score']}]")
        print(f"切片: {r['text'][:120]}...")
        print(f"完整上下文长度: {len(r['full_context'])} 字")