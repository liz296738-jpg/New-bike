# 🎓 小泽学长 - 西南科技大学新生答疑助手

基于 **RAG（检索增强生成）** 的校园知识问答系统。前端 Vue3 + Tailwind，后端 FastAPI + ChromaDB + DeepSeek。

## 🏗️ 架构

```
frontend/  (Vite + Vue3 + Tailwind CSS)
    │  POST /chat SSE 流式
    ▼
backend/  (FastAPI)
    │  ChromaDB 检索 Top-3
    │  DeepSeek chat API
    ▼
    SSE: data: {"content":"..."}
```

## 🚀 快速启动

### 后端

```bash
cd backend
cp .env.example .env          # 填入 DEEPSEEK_API_KEY
pip install -r requirements.txt
python ingest_data.py          # 首次：切片 + 向量化知识库
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev                    # http://localhost:3000
```

## 📁 项目结构

```
├── backend/
│   ├── main.py                # FastAPI 入口 + /chat SSE 接口
│   ├── ingest_data.py         # Markdown → 切片 → ChromaDB
│   ├── requirements.txt
│   ├── .env.example
│   └── data/
│       ├── knowledge/         # 校园 Markdown 资料
│       └── chroma_db/         # 向量库（不入 git）
└── frontend/
    ├── src/
    │   ├── App.vue            # 聊天主界面
    │   ├── main.js
    │   └── assets/main.css
    ├── index.html
    ├── package.json
    ├── tailwind.config.js
    └── vite.config.js
```

## ⚙️ 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3, Vite, Tailwind CSS, markdown-it |
| 后端 | FastAPI, LangChain, ChromaDB |
| 模型 | DeepSeek Chat API + all-MiniLM-L6-v2 (embedding) |
| 协议 | Server-Sent Events (SSE) 流式传输 |
