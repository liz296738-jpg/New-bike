<template>
  <div class="flex flex-col h-[100dvh] bg-gray-100 overflow-hidden">
    <!-- ═══════════════════════════════════════════════════════════ -->
    <!--  顶部导航栏                                                -->
    <!-- ═══════════════════════════════════════════════════════════ -->
    <header
      class="
        flex-shrink-0 h-14 px-4
        bg-gradient-to-r from-campus-600 to-campus-700
        shadow-md flex items-center justify-between
        z-30
      "
    >
      <div class="flex items-center gap-2 min-w-0">
        <span class="text-xl flex-shrink-0">🎓</span>
        <h1
          class="text-white font-semibold text-[15px] sm:text-[17px] truncate"
        >
          小泽学长 - 西南科技大学新生答疑
        </h1>
      </div>
      <button
        class="
          flex-shrink-0 ml-3 px-3 py-1.5 text-xs sm:text-sm
          bg-white/20 hover:bg-white/30 active:bg-white/40
          text-white rounded-lg transition-colors
          border border-white/30
        "
        @click="resetChat"
      >
        重置对话
      </button>
    </header>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <!--  对话区域                                                  -->
    <!-- ═══════════════════════════════════════════════════════════ -->
    <main
      ref="chatContainer"
      class="flex-1 overflow-y-auto px-4 py-4 scroll-smooth"
    >
      <div class="max-w-3xl mx-auto">
        <!-- 空态引导 -->
        <div
          v-if="messages.length === 0"
          class="flex flex-col items-center justify-center pt-16 sm:pt-24 text-center"
        >
          <div
            class="
              w-20 h-20 sm:w-24 sm:h-24 rounded-full
              bg-gradient-to-br from-campus-100 to-campus-200
              flex items-center justify-center mb-5
              shadow-sm
            "
          >
            <span class="text-4xl sm:text-5xl">🎓</span>
          </div>
          <h2 class="text-lg sm:text-xl font-semibold text-gray-800 mb-2">
            嗨！我是小泽学长 👋
          </h2>
          <p class="text-sm sm:text-base text-gray-500 max-w-xs leading-relaxed">
            关于西南科技大学的一切 —<br />宿舍、食堂、课程、校园生活，尽管问我！
          </p>
        </div>

        <!-- 消息列表 -->
        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="flex gap-2 sm:gap-3 mb-5 animate-fade-in"
          :class="msg.role === 'user'
            ? 'flex-row-reverse'
            : 'flex-row'"
        >
          <!-- AI 头像 -->
          <div
            v-if="msg.role === 'assistant'"
            class="
              flex-shrink-0 w-8 h-8 sm:w-9 sm:h-9 rounded-lg
              bg-gradient-to-br from-campus-400 to-campus-600
              flex items-center justify-center text-white
              text-xs sm:text-sm font-bold shadow-sm
            "
          >
            泽
          </div>

          <!-- 气泡 -->
          <div
            class="max-w-[85%] sm:max-w-[75%]"
          >
            <div
              class="px-3.5 py-2.5 rounded-2xl text-[14px] sm:text-[15px] leading-relaxed break-words"
              :class="msg.role === 'user'
                ? 'bg-campus-500 text-white rounded-br-md'
                : 'bg-white text-gray-800 rounded-bl-md shadow-sm border border-gray-100'"
            >
              <!-- AI 消息用 v-html 渲染 Markdown -->
              <div
                v-if="msg.role === 'assistant'"
                class="markdown-body"
                :class="{ 'typing-cursor': idx === streamIdx }"
                v-html="msg.rendered"
              />
              <!-- 用户消息纯文本 -->
              <span v-else class="whitespace-pre-wrap">{{ msg.content }}</span>
            </div>
          </div>

          <!-- 用户头像（占位对称） -->
          <div
            v-if="msg.role === 'user'"
            class="
              flex-shrink-0 w-8 h-8 sm:w-9 sm:h-9 rounded-lg
              bg-gradient-to-br from-emerald-300 to-emerald-500
              flex items-center justify-center text-white
              text-xs sm:text-sm font-bold shadow-sm
            "
          >
            我
          </div>
        </div>

        <!-- 打字中指示器 -->
        <div v-if="isStreaming && !streamIdx" class="flex gap-2 sm:gap-3 mb-5">
          <div
            class="
              flex-shrink-0 w-8 h-8 sm:w-9 sm:h-9 rounded-lg
              bg-gradient-to-br from-campus-400 to-campus-600
              flex items-center justify-center text-white font-bold shadow-sm
            "
          >
            泽
          </div>
          <div class="bg-white rounded-2xl rounded-bl-md px-4 py-3 shadow-sm border border-gray-100">
            <div class="flex gap-1.5">
              <span class="w-2 h-2 rounded-full bg-gray-300 animate-dot-pulse" />
              <span class="w-2 h-2 rounded-full bg-gray-300 animate-dot-pulse" style="animation-delay:0.2s" />
              <span class="w-2 h-2 rounded-full bg-gray-300 animate-dot-pulse" style="animation-delay:0.4s" />
            </div>
          </div>
        </div>

        <!-- 底部留白 -->
        <div class="h-4" />
      </div>
    </main>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <!--  快捷问题                                                  -->
    <!-- ═══════════════════════════════════════════════════════════ -->
    <div class="flex-shrink-0 bg-gray-100/90 backdrop-blur-sm">
      <div class="max-w-3xl mx-auto px-4">
        <div
          ref="quickBar"
          class="
            flex gap-2 py-2.5 overflow-x-auto scrollbar-none
            snap-x snap-mandatory
          "
        >
          <button
            v-for="(q, i) in quickQuestions"
            :key="i"
            class="
              flex-shrink-0 snap-start
              px-3.5 py-1.5 text-[13px] sm:text-sm
              bg-white border border-campus-200 text-campus-700
              rounded-full shadow-sm
              hover:bg-campus-50 active:bg-campus-100
              transition-colors whitespace-nowrap
            "
            @click="sendQuick(q)"
          >
            {{ q }}
          </button>
        </div>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════════ -->
    <!--  输入区域                                                  -->
    <!-- ═══════════════════════════════════════════════════════════ -->
    <footer class="flex-shrink-0 bg-gray-100 border-t border-gray-200 pb-safe">
      <div class="max-w-3xl mx-auto px-4 py-3">
        <div class="flex items-end gap-2.5">
          <!-- 输入框 -->
          <div class="flex-1 relative">
            <textarea
              ref="inputEl"
              v-model="inputText"
              :disabled="isStreaming"
              :rows="inputRows"
              class="
                w-full resize-none rounded-xl border border-gray-300
                px-3.5 py-2.5 text-[15px] leading-relaxed
                focus:outline-none focus:ring-2 focus:ring-campus-400
                focus:border-transparent
                placeholder:text-gray-400
                disabled:bg-gray-50 disabled:text-gray-400
                transition-shadow
              "
              placeholder="输入你的问题..."
              @keydown.enter.exact.prevent="sendMessage"
              @input="onInputChange"
            />
          </div>

          <!-- 发送按钮 -->
          <button
            class="
              flex-shrink-0 h-10 px-4 rounded-xl
              text-sm font-medium
              transition-all duration-200
              flex items-center justify-center
            "
            :class="canSend
              ? 'bg-campus-500 hover:bg-campus-600 active:bg-campus-700 text-white shadow-sm'
              : 'bg-gray-200 text-gray-400 cursor-not-allowed'"
            :disabled="!canSend"
            @click="sendMessage"
          >
            <span v-if="!isStreaming">发送</span>
            <span v-else class="flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-white/60 animate-dot-pulse" />
              <span>回复中</span>
            </span>
          </button>
        </div>
        <!-- 提示 -->
        <p class="text-[11px] text-gray-400 mt-1.5 text-center">
          小泽学长由 AI 驱动，回复仅供参考 📚
        </p>
      </div>
    </footer>
  </div>
</template>

<!-- ═══════════════════════════════════════════════════════════════ -->
<!--  SCRIPT                                                        -->
<!-- ═══════════════════════════════════════════════════════════════ -->
<script setup>
import { ref, reactive, computed, nextTick, watch } from 'vue'
import MarkdownIt from 'markdown-it'

// ── 常量 ────────────────────────────────────────────────────
const CHAT_URL = 'http://127.0.0.1:8000/chat'

const quickQuestions = [
  '宿舍条件怎么样？',
  '一食堂有什么好吃的？',
  '到绵阳站怎么走？',
  '图书馆开放时间？',
  '有哪些社团可以加入？',
  '学校周边有什么好玩的？',
]

// ── markdown-it 实例（禁用原始 HTML 保证安全） ─────────────
const md = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: true,
})

// ── 状态 ────────────────────────────────────────────────────
const chatContainer = ref(null)
const inputEl = ref(null)
const messages = ref([])        // { role, content, rendered }
const inputText = ref('')
const isStreaming = ref(false)
const streamIdx = ref(-1)       // 正在流式输出的那条消息索引（-1 表示无）
const sessionId = ref(generateId())

// 输入框行数（自适应）
const inputRows = ref(1)

// ── 计算属性 ────────────────────────────────────────────────
const canSend = computed(() =>
  inputText.value.trim().length > 0 && !isStreaming.value
)

// ── ID 生成 ─────────────────────────────────────────────────
function generateId() {
  return `web_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

// ── 重置对话 ────────────────────────────────────────────────
function resetChat() {
  messages.value = []
  isStreaming.value = false
  streamIdx.value = -1
  sessionId.value = generateId()
  inputText.value = ''
  inputRows.value = 1
}

// ── 内容渲染：正则匹配 [图片: URL] → <img> + Markdown ──────
const IMAGE_RE = /\[图片:\s*([^\]]+)\]/g

function renderContent(raw) {
  let result = ''
  let lastIdx = 0
  let match
  IMAGE_RE.lastIndex = 0

  while ((match = IMAGE_RE.exec(raw)) !== null) {
    // 图片之前的文本 → Markdown 渲染
    if (match.index > lastIdx) {
      result += md.render(raw.slice(lastIdx, match.index))
    }
    // 图片 → 优雅 HTML
    result += `
      <img
        src="${escapeAttr(match[1])}"
        alt="校园图片"
        class="
          img-fade-in max-w-[260px] sm:max-w-[320px] w-full
          rounded-xl shadow-md my-2
          border border-gray-100
        "
        loading="lazy"
        onerror="this.style.display='none'"
      />`
    lastIdx = IMAGE_RE.lastIndex
  }

  // 剩余文本
  if (lastIdx < raw.length) {
    result += md.render(raw.slice(lastIdx))
  }

  return result
}

// 简单的属性转义（防 XSS）
function escapeAttr(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

// ── 输入框自适应高度 ────────────────────────────────────────
function onInputChange() {
  const lines = inputText.value.split('\n').length
  inputRows.value = Math.min(Math.max(lines, 1), 4)
}

// ── 发送消息 ────────────────────────────────────────────────
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  inputText.value = ''
  inputRows.value = 1

  // 追加用户消息
  messages.value.push({
    role: 'user',
    content: text,
    rendered: '',
  })
  await scrollToBottom()

  // 追加 AI 占位消息
  const aiMsg = reactive({
    role: 'assistant',
    content: '',
    rendered: '',
  })
  messages.value.push(aiMsg)
  const aiIdx = messages.value.length - 1

  // 标记流式输出
  isStreaming.value = true
  streamIdx.value = aiIdx

  try {
    await streamSSE(text, aiMsg)
  } finally {
    isStreaming.value = false
    streamIdx.value = -1

    // 空回复兜底
    if (!aiMsg.content) {
      aiMsg.content = '🤔 抱歉学弟/学妹，这个问题我暂时答不上来，要不换个问法试试？'
      aiMsg.rendered = renderContent(aiMsg.content)
    }
    await scrollToBottom()
  }
}

// ── 快捷发送 ────────────────────────────────────────────────
function sendQuick(q) {
  inputText.value = q
  sendMessage()
}

// ── SSE 流式请求（fetch + ReadableStream） ─────────────────
async function streamSSE(userMessage, aiMsg) {
  const resp = await fetch(CHAT_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: userMessage,
      session_id: sessionId.value,
    }),
  })

  if (!resp.ok) {
    throw new Error(`后端返回 HTTP ${resp.status}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed || !trimmed.startsWith('data:')) continue

      const payload = trimmed.slice(5).trim()
      if (payload === '[DONE]') continue

      try {
        const json = JSON.parse(payload)
        if (json.content) {
          aiMsg.content += json.content
          aiMsg.rendered = renderContent(aiMsg.content)
          await smartScroll()
        }
        if (json.error) {
          aiMsg.content = `[出错了] ${json.error}`
          aiMsg.rendered = renderContent(aiMsg.content)
        }
      } catch (_) {
        // 忽略非法 JSON 行
      }
    }
  }
}

// ── 智能滚动（仅当用户靠近底部时自动跟底） ────────────────
async function smartScroll() {
  await nextTick()
  const el = chatContainer.value
  if (!el) return
  // 距离底部 < 100px 时视为"在看最新消息"
  const distToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  if (distToBottom < 120) {
    el.scrollTop = el.scrollHeight
  }
}

async function scrollToBottom() {
  await nextTick()
  const el = chatContainer.value
  if (el) el.scrollTop = el.scrollHeight
}
</script>
