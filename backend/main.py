"""
校园知识库后端 — FastAPI 入口
小泽（西南科技大学大二学长）RAG 对话系统
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

from langchain_community.embeddings.sentence_transformer import (
    SentenceTransformerEmbeddings,
)
from langchain_community.vectorstores import Chroma

# ── 加载 .env 环境变量 ──────────────────────────────────────────
load_dotenv()

# ── 路径常量 ────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
CHROMA_DIR = BASE_DIR / "data" / "chroma_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── FastAPI 应用实例 ────────────────────────────────────────────
app = FastAPI(
    title="校园知识库 API",
    description="基于 RAG 的校园知识问答系统 — 小泽学长",
    version="0.2.0",
)

# ── CORS 跨域配置 ───────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 系统提示词（小泽人设）────────────────────────────────────────
SYSTEM_PROMPT = (
    "你叫小泽，是西南科技大学的大二学长。"
    "你热情、幽默、真诚，喜欢使用 Emoji。"
    "请务必根据检索到的西南科技大学背景资料回答新生的问题。"
    "如果资料中没有提到，请明确表示不知道，切勿捏造学校的规定或建筑。"
    "可以适时建议新生实地探索绵阳的校园。"
)

# ── 启动时加载向量库 & DeepSeek 客户端 ──────────────────────────

print("🧠 正在加载 embedding 模型与向量库...")
_embeddings = SentenceTransformerEmbeddings(model_name=EMBEDDING_MODEL)
_vectordb = Chroma(
    persist_directory=str(CHROMA_DIR),
    embedding_function=_embeddings,
)
_retriever = _vectordb.as_retriever(search_kwargs={"k": 3})

_deepseek_key = os.getenv("DEEPSEEK_API_KEY")
if not _deepseek_key:
    raise RuntimeError("❌ 未设置环境变量 DEEPSEEK_API_KEY，请在 .env 文件中配置。")

_client = OpenAI(
    api_key=_deepseek_key,
    base_url="https://api.deepseek.com",
)

print("✅ 初始化完成 — 小泽学长已上线 👋")


# ── 数据模型 ────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str


# ── 路由 ────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "校园知识库 API 运行中 — 小泽学长已上线 👋"}


@app.post("/chat")
def chat(req: ChatRequest):
    """
    SSE 流式对话接口。

    1. 从 ChromaDB 检索 Top-3 相关文档片段
    2. 将片段拼入上下文，交由 DeepSeek（小泽人设）生成回复
    3. 以 Server-Sent Events 流式返回
    """

    # ── 1. 检索相关文档 ─────────────────────────────────────
    docs = _retriever.invoke(req.message)

    if docs:
        context_parts = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "未知来源")
            context_parts.append(
                f"【资料片段 {i + 1}】（来源：{source}）\n{doc.page_content}"
            )
        context = "\n\n".join(context_parts)
    else:
        context = "（未检索到相关校园资料）"

    # ── 2. 组装消息 ─────────────────────────────────────────
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"以下是从西南科技大学资料库中检索到的背景信息：\n\n"
                f"{context}\n\n"
                f"请根据以上资料，以小泽学长的身份回答这位新生的问题。\n"
                f"新生提问：{req.message}"
            ),
        },
    ]

    # ── 3. 调用 DeepSeek（流式） ─────────────────────────────
    try:
        stream = _client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.7,
            stream=True,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DeepSeek API 调用失败：{e}")

    # ── 4. SSE 生成器 ───────────────────────────────────────
    def event_stream():
        try:
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    payload = json.dumps(
                        {"content": delta.content}, ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
        except Exception:
            error_payload = json.dumps(
                {"error": "流式响应中断，请重试。"}, ensure_ascii=False
            )
            yield f"data: {error_payload}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
