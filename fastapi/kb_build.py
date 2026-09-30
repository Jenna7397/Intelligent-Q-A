# -*- coding: utf-8 -*-
"""
侨乡知识库构建脚本 (ChromaDB 版)
将 CSV + Markdown 数据清洗、切片、打标签、向量化后存入 ChromaDB。
- CSV：从 kb_data/qiao/ 读取 4 个文件
- MD ：递归扫描 kb_data/md/ 下的 4 个子目录
存储路径：kb_store/chroma_db/
用法：python kb_build.py
"""
import csv
import os
os.environ["CHROMA_HNSWLIB_NO_NATIVE"] = "1"  
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HNSWLIB_NO_NATIVE"] = "1"
os.environ["ANONYMIZED_TELEMETRY"] = "False"
import re
import sys
from pathlib import Path

# 国内下载模型走 HuggingFace 镜像（必须在 import fastembed 前设置）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from dotenv import load_dotenv
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# 侨批长标题 → 短实体名（数据治理）
from kb_retriever import extract_remittance_short

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH)

# ---- 配置 ----
CSV_DIR = Path(os.getenv("KB_CSV_DIR", str(Path(__file__).resolve().parent.parent / "kb_data" / "qiao")))
MD_DIR = Path(os.getenv("KB_MD_DIR", str(Path(__file__).resolve().parent.parent / "kb_data" / "md")))
STORE_DIR = Path(os.getenv("CHROMA_DIR", str(Path(__file__).resolve().parent.parent / "kb_store")))
CHROMA_DB_PATH = STORE_DIR / "chroma_db"
COLLECTION_NAME = "chaoshan_knowledge"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

# CSV 文件 → (类型, 名称列, 正文列)
CSV_SOURCES = [
    ("persons.csv", "人物", "name", "简介"),
    ("hometowns.csv", "村落", "name", "story_summary"),
    ("houses.csv", "侨宅", "place", "summary"),
    ("remittances.csv", "侨批", "name", "summary"),
]

# MD 子目录名 → 中文类型标签
MD_FOLDER_TYPE_MAP = {
    "overseas_chinese": "侨胞",
    "remittances":      "侨批",
    "overseas_houses":  "侨宅",
    "hometowns":        "侨乡",
}

MAX_CHUNK_CHARS = 400  # 每个切片最大字符数


# ==================== 1. CSV 处理 ====================

def split_csv_text(text: str, name: str, type_: str) -> list:
    """CSV 切片：按句子切分，每个切片前面加【名称】前缀，保留上下文主体。"""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[。！？；])", text)
    chunks, cur = [], ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(cur) + len(p) <= MAX_CHUNK_CHARS:
            cur += p
        else:
            if cur:
                chunks.append(f"关于{type_}【{name}】：{cur}")
            while len(p) > MAX_CHUNK_CHARS:
                chunks.append(f"关于{type_}【{name}】：{p[:MAX_CHUNK_CHARS]}")
                p = p[MAX_CHUNK_CHARS:]
            cur = p
    if cur:
        chunks.append(f"关于{type_}【{name}】：{cur}")
    return chunks


def load_csv_documents():
    """读取全部 CSV，返回 list of {text, metadata, id}"""
    documents = []
    if not CSV_DIR.exists():
        print(f"[跳过] CSV 目录不存在：{CSV_DIR}")
        return documents

    for filename, type_, name_col, text_col in CSV_SOURCES:
        path = CSV_DIR / filename
        if not path.exists():
            print(f"[跳过] 找不到 {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                name = (row.get(name_col) or "").strip() or f"{type_}未知{i}"
                # 侨批长标题 → 短实体名（供展示/精确匹配）；其余类型 name_short = name
                name_short = extract_remittance_short(name) if filename == "remittances.csv" else name
                text = (row.get(text_col) or "").strip()
                if not text:
                    continue
                full_text = text
                for j, chunk in enumerate(split_csv_text(text, name, type_)):
                    documents.append({
                        "text": chunk,
                        "metadata": {
                            "type": type_,
                            "name": name,
                            "name_short": name_short,
                            "source": filename,
                            "full_context": full_text,
                        },
                        "id": f"csv_{type_}_{i}_{j}",
                    })
        print(f"[完成] {filename}（{type_}）")
    return documents


# ==================== 2. Markdown 处理（递归子目录） ====================

def load_md_documents():
    """递归扫描 MD_DIR 下的子目录，按子目录名映射 type 标签。"""
    documents = []
    if not MD_DIR.exists():
        print(f"[跳过] Markdown 目录不存在：{MD_DIR}")
        return documents

    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_CHUNK_CHARS,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )

    for sub_dir in sorted(MD_DIR.iterdir()):
        if not sub_dir.is_dir():
            continue

        folder_name = sub_dir.name
        type_label = MD_FOLDER_TYPE_MAP.get(folder_name, folder_name)
        md_files = sorted(sub_dir.glob("*.md"))
        if not md_files:
            print(f"[跳过] {folder_name}/ 没有 md 文件")
            continue

        print(f"[处理] {folder_name}/ （{type_label}）共 {len(md_files)} 个文件")

        for md_file in md_files:
            # 实体名：取文件名（去掉《》书名号），如《东观楼：...》.md → 东观楼：...
            entity_name = md_file.stem.strip("《》").strip()
            with open(md_file, "r", encoding="utf-8") as f:
                md_text = f.read()

            md_splits = md_splitter.split_text(md_text)
            for i, split in enumerate(md_splits):
                h1 = split.metadata.get("Header 1", "")
                h2 = split.metadata.get("Header 2", "")
                h3 = split.metadata.get("Header 3", "")
                section = f"{h1} - {h2} - {h3}".strip(" -") or "正文"

                sub_chunks = text_splitter.split_text(split.page_content)
                for j, chunk in enumerate(sub_chunks):
                    if not chunk.strip():
                        continue
                    documents.append({
                        "text": chunk,
                        "metadata": {
                            "type": type_label,
                            "source": md_file.name,
                            "folder": folder_name,
                            "section": section,
                            "name": entity_name,
                            "full_context": chunk,
                        },
                        "id": f"md_{folder_name}_{md_file.stem}_{i}_{j}",
                    })
    print(f"[完成] Markdown 共生成 {len(documents)} 个切片")
    return documents


# ==================== 3. 写入 ChromaDB ====================

def build_chroma_db(documents: list):
    if not documents:
        print("没有可用数据，终止。")
        sys.exit(1)

    print(f"\n共生成 {len(documents)} 个知识块，开始向量化...")

    from fastembed import TextEmbedding
    print(f"正在加载 Embedding 模型：{EMBEDDING_MODEL}")
    model = TextEmbedding(model_name=EMBEDDING_MODEL)

    texts = [doc["text"] for doc in documents]
    print("正在向量化（首次运行需下载模型，约 100MB）...")
    embeddings = [e.tolist() for e in model.embed(texts)]
    print(f"向量化完成，维度：{len(embeddings[0])}")

    import chromadb
    CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))

    # 自动清空旧 collection
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"已删除旧的 collection：{COLLECTION_NAME}")
    except Exception:
        pass

    # 修复记录(2026-09-25)：HNSW 近似索引默认搜索宽度(search_ef)不足，
    # 候选池 n_results<=20 时会漏召回真正的最近邻（诊断：同向量 n=30 rank1、n=20 不在）。
    # 显式配置 construction_ef/search_ef=200，保证小候选池下召回稳定。
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine",
            "hnsw:construction_ef": 200,
            "hnsw:search_ef": 200,
        },
    )

    BATCH_SIZE = 100
    total = len(documents)
    print(f"DEBUG >>> 进入写入阶段 total={total}, embeddings长度={len(embeddings)}, collection={collection.name}", flush=True)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        batch = documents[start:end]
        collection.add(
            ids=[d["id"] for d in batch],
            embeddings=embeddings[start:end],
            documents=[d["text"] for d in batch],
            metadatas=[d["metadata"] for d in batch],
        )
        print(f"  已写入 {end}/{total} 条")

    print(f"\n 知识库构建完成！共 {total} 条")
    print(f" 存储位置：{CHROMA_DB_PATH}")


# ==================== 4. 主函数 ====================

def main():
    print("=" * 56)
    print("开始构建侨乡知识库 (ChromaDB 版)")
    print(f"CSV 目录    ：{CSV_DIR}")
    print(f"MD  目录    ：{MD_DIR}")
    print(f"存储目录    ：{CHROMA_DB_PATH}")
    print(f"Embedding   ：{EMBEDDING_MODEL}")
    print("=" * 56)

    csv_docs = load_csv_documents()
    md_docs = load_md_documents()
    all_docs = csv_docs + md_docs

    build_chroma_db(all_docs)


if __name__ == "__main__":
    main()