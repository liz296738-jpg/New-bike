"""
独立脚本：将 data/knowledge 下的 Markdown 文件切片并向量化，
持久化存储到 data/chroma_db。
"""

import os
import sys
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.embeddings.sentence_transformer import (
    SentenceTransformerEmbeddings,
)
from langchain_community.vectorstores import Chroma


# ── 路径常量 ───────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "data" / "knowledge"
CHROMA_DIR = BASE_DIR / "data" / "chroma_db"

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# 使用轻量本地 embedding 模型（all-MiniLM-L6-v2，约 80 MB）
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def ingest():
    # ── 1. 检查知识目录 ────────────────────────────────────────
    if not KNOWLEDGE_DIR.exists():
        print(f"❌ 知识目录不存在：{KNOWLEDGE_DIR}")
        sys.exit(1)

    md_files = list(KNOWLEDGE_DIR.glob("*.md"))
    if not md_files:
        print(f"⚠️  知识目录下没有 .md 文件：{KNOWLEDGE_DIR}")
        print("   请放入 Markdown 格式的校园资料后重新运行。")
        sys.exit(0)

    print(f"📂 找到 {len(md_files)} 个 Markdown 文件：")
    for f in md_files:
        print(f"   - {f.name}")

    # ── 2. 加载文档 ────────────────────────────────────────────
    print("\n📄 正在加载文档...")
    loader = DirectoryLoader(
        str(KNOWLEDGE_DIR),
        glob="*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    documents = loader.load()
    print(f"   共加载 {len(documents)} 篇文档")

    # ── 3. 文本切片 ────────────────────────────────────────────
    print(f"\n✂️  正在切片（chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}）...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    print(f"   共生成 {len(chunks)} 个文本块")

    # ── 4. 创建 embedding 模型 ─────────────────────────────────
    print(f"\n🧠 正在加载 embedding 模型（{EMBEDDING_MODEL}）...")
    print("   首次运行将自动下载模型（约 80 MB），请稍候...")
    embeddings = SentenceTransformerEmbeddings(model_name=EMBEDDING_MODEL)

    # ── 5. 向量化并持久化到 Chroma ─────────────────────────────
    print(f"\n💾 正在向量化并存储到 {CHROMA_DIR} ...")
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    vectordb = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    # Chroma 新版本中 from_documents 已自动持久化；手动 persist 确保落盘
    # （旧版本需要手动调用，这里做兼容处理）
    if hasattr(vectordb, "persist"):
        vectordb.persist()

    print(f"\n✅ 摄入完成！向量数据库已保存到 {CHROMA_DIR}")
    print(f"   文档数：{len(documents)}，文本块数：{len(chunks)}")


if __name__ == "__main__":
    ingest()
