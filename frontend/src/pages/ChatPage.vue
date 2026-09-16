<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import AgentInspector from '../components/AgentInspector.vue'
import OnboardingTour, { type TourStep } from '../components/OnboardingTour.vue'
import {
  createMemory,
  deleteConversation,
  getCharacterPool,
  getConversationMessages,
  getConversations,
  replaceCharacterPool,
  setCharacterFavorite,
} from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useChatTaskStore } from '../stores/chatTasks'
import { useUiStore } from '../stores/ui'
import { hasCompletedOnboarding, markOnboardingComplete } from '../utils/onboarding'
import type {
  AgentAction,
  AIResponse,
  Conversation,
  FavoriteCharacterSuggestion,
  MemorySuggestion,
  StoredChatMessage,
} from '../types/ai'

type DisplayMessage = {
  key: string
  role: 'user' | 'assistant'
  content: string
  response?: AIResponse
}

const auth = useAuthStore()
const tasks = useChatTaskStore()
const ui = useUiStore()
const route = useRoute()
const router = useRouter()

const agentLabels: Record<string, string> = {
  fc_main_agent: '黑塔 · 主控大脑',
  react_main_agent: '黑塔 · 主 Agent',
  herta_main_agent: '黑塔主 Agent',
}

function agentLabel(name?: string | null) {
  if (!name) return '黑塔'
  return agentLabels[name] ?? name
}

function statusLabel(status?: string | null) {
  if (status === 'verified') return '有据可查'
  if (status === 'unverified') return '未经检索验证'
  return status ?? ''
}
const greeting =
  '我是黑塔，现在你们列车的智库由本天才来接管，有什么事问我就行了。'
const prompt = ref('')
const submitting = ref(false)
const anonymousLoading = ref(false)
const historyLoading = ref(false)
const error = ref('')
const activeConversationId = ref('')
const conversations = ref<Conversation[]>([])
const messages = ref<DisplayMessage[]>([])
const savingSuggestion = ref('')
const savedSuggestions = ref(new Set<string>())
const savingFavorite = ref('')
const savedFavorites = ref(new Set<string>())
const latestResponse = computed(() => {
  const item = [...messages.value].reverse().find((message) => message.response)
  return item?.response ?? null
})
const activeBackgroundJobs = computed(() =>
  tasks.activeJobs.filter((job) =>
    !activeConversationId.value || job.conversation_id === activeConversationId.value),
)
const activeJob = computed(() => activeBackgroundJobs.value[0] ?? null)
const liveStep = computed(() => {
  const job = activeJob.value
  if (!job) return null
  const events = tasks.events[job.id] ?? []
  const last = events[events.length - 1]
  return last ? { title: last.title, detail: last.detail || '' } : null
})
const streamingAnswer = computed(() => {
  const job = activeJob.value
  if (!job) return ''
  return tasks.partialAnswers[job.id] || job.partial_answer || ''
})
const loading = computed(() => anonymousLoading.value || activeBackgroundJobs.value.length > 0)
const tourActive = ref(false)
const tourSteps: TourStep[] = [
  {
    title: '欢迎登车，开拓者',
    content: '我是黑塔，这座智库由本天才亲自接管。第一次来的话，花 30 秒跟我转一圈，马上就能开工。',
  },
  {
    target: 'sidebar-nav',
    title: '功能入口都在这里',
    content: '游戏智库、剧情档案、智能配队、养成规划……想用什么点一下就能跳转，侧边栏也可以随时收起。',
  },
  {
    target: 'composer',
    title: '有问题，直接问我',
    content: '在输入框里用大白话提问就行：突破材料、配队推荐、剧情关系、活动攻略都可以。我会自己思考，再调度对应的专家 Agent 去查证。',
  },
  {
    target: 'inspector-toggle',
    title: '我的思考过程全透明',
    content: '回答生成时点右上角「Agent 过程」，可以实时看到我的每一步思考和工具调用。',
  },
  {
    target: 'history-panel',
    title: '对话会自动留档',
    content: '每段会话都保存在这里，随时回来接着聊；你的玩法偏好也能存成长期记忆，我会记得。',
  },
  {
    title: '准备完毕',
    content: '现在就可以试试问我：「流萤突破要什么材料」或者「帮我配一支不用限定五星的队」。祝开拓顺利！',
    buttonLabel: '开始使用',
  },
]

function finishTour() {
  tourActive.value = false
  if (auth.user) markOnboardingComplete(auth.user.id)
}
const entityLabels: Record<string, string> = {
  character: '角色智库',
  item: '物品智库',
  lightcone: '光锥智库',
  relic: '遗器智库',
  story: '剧情档案',
  activity: '活动档案',
}
const entityIcons: Record<string, string> = {
  character: '角',
  item: '物',
  lightcone: '锥',
  relic: '遗',
  story: '剧',
  activity: '活',
}

function newConversation() {
  activeConversationId.value = ''
  messages.value = []
  error.value = ''
}

function sendFollowUp(question: string) {
  if (!question.trim() || submitting.value) return
  prompt.value = question.trim()
  void submit()
}

function runAction(action: AgentAction) {
  const hasParams = action.params && Object.keys(action.params).length > 0
  void router.push({
    path: action.target_url,
    query: hasParams ? action.params : undefined,
  })
}

async function refreshConversations() {
  if (!auth.isAuthenticated) return
  conversations.value = await getConversations()
}

async function openConversation(id: string) {
  historyLoading.value = true
  error.value = ''
  try {
    const result = await getConversationMessages(id)
    activeConversationId.value = result.conversation.id
    messages.value = result.items.map((item: StoredChatMessage) => ({
      key: item.id,
      role: item.role,
      content: item.content,
      response: item.response,
    }))
  } catch {
    error.value = '这段会话没能读取出来，可能已经被删除。'
  } finally {
    historyLoading.value = false
  }
}

async function removeConversation(id: string) {
  await deleteConversation(id)
  if (activeConversationId.value === id) newConversation()
  await refreshConversations()
}

async function submit() {
  const question = prompt.value.trim()
  if (!question || submitting.value) return
  const temporaryHistory = messages.value.slice(-12).map((message) => ({
    role: message.role,
    content: message.content,
  }))
  const localKey = `local-${Date.now()}`
  messages.value.push({ key: `${localKey}-user`, role: 'user', content: question })
  prompt.value = ''
  submitting.value = true
  error.value = ''
  try {
    if (auth.isAuthenticated) {
      const job = await tasks.submitLogged(
        question,
        activeConversationId.value,
        temporaryHistory,
      )
      activeConversationId.value = job.conversation_id
    } else {
      anonymousLoading.value = true
      const response = await tasks.submitAnonymous(question, temporaryHistory)
      messages.value.push({
        key: response.response_id,
        role: 'assistant',
        content: response.answer,
        response,
      })
    }
    await refreshConversations()
  } catch (err) {
    messages.value = messages.value.filter((message) => message.key !== `${localKey}-user`)
    error.value = axios.isAxiosError(err) && err.response?.status === 422
      ? '问题格式没有通过校验。单次提问最多 4000 字；也可以新建会话后重试。'
      : '智库连接出了点问题。确认后端和检索服务正常后再试。'
  } finally {
    submitting.value = false
    anonymousLoading.value = false
  }
}

function onComposerKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return
  event.preventDefault()
  void submit()
}

function suggestionKey(item: MemorySuggestion) {
  return `${item.memory_type}:${item.content}`
}

async function confirmSuggestion(item: MemorySuggestion) {
  const key = suggestionKey(item)
  savingSuggestion.value = key
  try {
    await createMemory(item.memory_type, item.content)
    savedSuggestions.value = new Set([...savedSuggestions.value, key])
  } catch {
    error.value = '记忆保存失败，请在记忆管理页重试。'
  } finally {
    savingSuggestion.value = ''
  }
}

function memoryActionLabel(item: MemorySuggestion) {
  const labels: Record<MemorySuggestion['memory_type'], string> = {
    playstyle_preference: '保存玩法偏好',
    resource_priority: '保存资源优先级',
    favorite_character: '保存喜欢角色',
    usual_team: '保存常用队伍偏好',
    answer_preference: '保存回答偏好',
  }
  return labels[item.memory_type]
}

async function confirmFavorite(item: FavoriteCharacterSuggestion) {
  savingFavorite.value = item.character_id
  error.value = ''
  try {
    if (!item.is_owned) {
      const pool = await getCharacterPool()
      await replaceCharacterPool([
        ...pool.items.map((character) => character.character_id),
        item.character_id,
      ])
    }
    await setCharacterFavorite(item.character_id, true)
    savedFavorites.value = new Set([...savedFavorites.value, item.character_id])
  } catch {
    error.value = `没能把 ${item.name} 加入喜欢角色，请到角色智库重试。`
  } finally {
    savingFavorite.value = ''
  }
}

onMounted(async () => {
  if (auth.isAuthenticated) {
    try {
      await refreshConversations()
    } catch {
      error.value = '会话历史暂时无法读取，但仍可以开始新对话。'
    }
  }
  const requestedConversation = String(route.query.conversation || '')
  if (requestedConversation) await openConversation(requestedConversation)
  // 首次使用（按用户 id 记忆，访客无 auth.user 永不触发）时弹出新手引导；稍等布局稳定后再亮起。
  // 记档放在展示时刻而非完成时刻：中途刷新/关页也不会导致下次重弹。
  if (auth.user && !hasCompletedOnboarding(auth.user.id)) {
    window.setTimeout(() => {
      if (auth.user) markOnboardingComplete(auth.user.id)
      tourActive.value = true
    }, 600)
  }
})

watch(
  () => route.query.conversation,
  (conversationId) => {
    if (conversationId) void openConversation(String(conversationId))
  },
)

watch(
  () => tasks.lastCompletedJobId,
  (jobId) => {
    const job = tasks.jobs[jobId]
    if (job && job.conversation_id === activeConversationId.value) {
      void openConversation(job.conversation_id).then(refreshConversations)
    }
  },
)
</script>

<template>
  <AppShell page-class="chat-workspace">
    <template #inspector>
      <AgentInspector
        :conversation-id="activeConversationId"
        :fallback-response="latestResponse"
      />
    </template>
    <div class="chat-layout" :class="{ 'chat-layout--solo': !auth.isAuthenticated }">
      <aside v-if="auth.isAuthenticated" class="history-panel" data-tour="history-panel" aria-label="会话历史">
        <div class="history-head">
          <div>
            <span class="eyebrow">MEMORY LOG</span>
            <h2>会话历史</h2>
          </div>
          <button type="button" class="mini-action" @click="newConversation">＋ 新会话</button>
        </div>
        <p v-if="historyLoading" class="muted">正在读取记录…</p>
        <button
          v-for="item in conversations"
          :key="item.id"
          type="button"
          class="history-item"
          :class="{ active: item.id === activeConversationId }"
          @click="openConversation(item.id)"
        >
          <span>{{ item.title }}</span>
          <small>{{ new Date(item.updated_at).toLocaleDateString() }}</small>
          <i
            role="button"
            tabindex="0"
            aria-label="删除会话"
            @click.stop="removeConversation(item.id)"
            @keydown.enter.stop="removeConversation(item.id)"
          >×</i>
        </button>
        <p v-if="!conversations.length" class="history-empty">
          第一段对话会在你发送消息后保存。
        </p>
        <router-link class="memory-link" to="/profile/memories">管理长期记忆 →</router-link>
      </aside>

      <section class="chat-main">
        <header>
          <div>
            <span class="eyebrow">HERTA INTELLIGENCE NETWORK</span>
            <h1>列车智库已接管</h1>
          </div>
          <span class="agent-badge">黑塔 · 主 Agent</span>
        </header>

        <section class="conversation" aria-label="与黑塔对话">
          <div class="message assistant-message">
            <span class="avatar">H</span>
            <div class="message-content">
              <small>黑塔 · 主 Agent</small>
              <p>{{ greeting }}</p>
            </div>
          </div>

          <div
            v-for="message in messages"
            :key="message.key"
            class="message"
            :class="message.role === 'user' ? 'user-message' : 'assistant-message response-message'"
          >
            <span v-if="message.role === 'assistant'" class="avatar">H</span>
            <div class="message-content">
              <small>{{ message.role === 'user' ? '你' : '黑塔 · 主 Agent' }}</small>
              <p class="answer-text">{{ message.content }}</p>
              <div v-if="message.response" class="answer-meta">
                <span>{{ statusLabel(message.response.validation.status) }}</span>
                <span>{{ message.response.citations.length }} 条证据</span>
                <span>{{ agentLabel(message.response.agent) }}</span>
                <button
                  type="button"
                  class="process-toggle"
                  aria-label="展开查看本轮执行过程"
                  @click="ui.toggleInspector()"
                >
                  查看过程 →
                </button>
              </div>
              <nav
                v-if="message.response?.related_entities?.length"
                class="related-entities"
                aria-label="相关智库档案"
              >
                <router-link
                  v-for="item in message.response.related_entities"
                  :key="`${item.entity_type}-${item.entity_id}`"
                  :to="item.entity_url"
                >
                  <img
                    v-if="item.image_url"
                    :src="item.image_url"
                    :alt="item.name"
                  />
                  <i v-else class="entity-placeholder" aria-hidden="true">
                    {{ entityIcons[item.entity_type] ?? '档' }}
                  </i>
                  <span>
                    <small>{{ entityLabels[item.entity_type] ?? '相关档案' }}</small>
                    <strong>{{ item.entity_type === 'story' ? item.name : `进入 ${item.name} 档案` }}</strong>
                  </span>
                  <b aria-hidden="true">→</b>
                </router-link>
              </nav>
              <div
                v-if="message.response?.follow_up_questions?.length"
                class="follow-up-chips"
              >
                <button
                  v-for="question in message.response.follow_up_questions"
                  :key="question"
                  type="button"
                  class="follow-up-chip"
                  :disabled="submitting"
                  @click="sendFollowUp(question)"
                >
                  {{ question }}
                </button>
              </div>
              <div
                v-if="message.response?.actions?.length"
                class="agent-actions"
                aria-label="主 Agent 页面动作"
              >
                <button
                  v-for="action in message.response.actions"
                  :key="`${action.target_url}-${action.title}`"
                  type="button"
                  :title="action.description || action.title"
                  @click="runAction(action)"
                >
                  <span aria-hidden="true">{{
                    action.action_type === 'prefill' ? '⇢' : '→'
                  }}</span>
                  {{ action.title }}
                </button>
              </div>
              <div
                v-if="message.response?.memory_suggestions?.length"
                class="memory-suggestions"
              >
                <strong>检测到可长期使用的偏好，是否保存？</strong>
                <article
                  v-for="item in message.response.memory_suggestions"
                  :key="suggestionKey(item)"
                >
                  <span>{{ item.content }}</span>
                  <button
                    type="button"
                    :disabled="
                      savingSuggestion === suggestionKey(item) ||
                      savedSuggestions.has(suggestionKey(item))
                    "
                    @click="confirmSuggestion(item)"
                  >
                    {{
                      savedSuggestions.has(suggestionKey(item))
                        ? '已确认'
                        : savingSuggestion === suggestionKey(item)
                          ? '保存中…'
                          : memoryActionLabel(item)
                    }}
                  </button>
                </article>
              </div>
              <div
                v-if="message.response?.favorite_character_suggestions?.length"
                class="memory-suggestions favorite-suggestions"
              >
                <article
                  v-for="item in message.response.favorite_character_suggestions"
                  :key="item.character_id"
                >
                  <span>{{ item.prompt }}</span>
                  <button
                    type="button"
                    :disabled="
                      savingFavorite === item.character_id ||
                      savedFavorites.has(item.character_id)
                    "
                    @click="confirmFavorite(item)"
                  >
                    {{
                      savedFavorites.has(item.character_id)
                        ? '已设为喜欢'
                        : savingFavorite === item.character_id
                          ? '保存中…'
                          : item.is_owned
                            ? `喜欢 ${item.name}`
                            : '加入角色池并喜欢'
                    }}
                  </button>
                </article>
              </div>
            </div>
          </div>

          <div v-if="loading" class="message assistant-message response-message">
            <span class="avatar">H</span>
            <div class="message-content thinking">
              <small>黑塔正在思考</small>
              <div v-if="liveStep" class="live-step">
                <strong>{{ liveStep.title }}</strong>
                <p v-if="liveStep.detail">{{ liveStep.detail }}</p>
              </div>
              <p v-if="streamingAnswer" class="answer-text">{{ streamingAnswer }}</p>
              <p v-else-if="!liveStep">问答已在后台运行，你可以继续浏览其他智库页面。</p>
            </div>
          </div>
        </section>

        <form class="composer" data-tour="composer" @submit.prevent="submit">
          <textarea
            v-model="prompt"
            maxlength="4000"
            aria-label="输入问题"
            placeholder="问黑塔角色、配队、养成、材料或攻略问题……"
            rows="2"
            @keydown="onComposerKeydown"
          />
          <button type="submit" :disabled="submitting || !prompt.trim()">
            {{ submitting ? '提交中' : '发送' }} <span>→</span>
          </button>
        </form>
        <p v-if="error" class="error">{{ error }}</p>
      </section>
    </div>
  </AppShell>
  <OnboardingTour v-if="tourActive" :steps="tourSteps" @finish="finishTour" />
</template>

<style scoped>
.chat-layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 20px; height: 100%; min-height: 0; }
.chat-layout--solo { grid-template-columns: minmax(0, 1fr); }
.chat-main { display: grid; grid-template-rows: auto minmax(0, 1fr) auto auto; min-width: 0; min-height: 0; }
.chat-main > header { margin-bottom: 20px; }
.history-panel { min-height: 0; padding: 14px; overflow-y: auto; overscroll-behavior: contain; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); }
.history-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; margin-bottom: 16px; }
.history-head h2 { margin: 4px 0 0; font-size: 1.15rem; }
.mini-action { border: 1px solid var(--line-strong); background: rgba(233, 200, 117, .08); color: var(--gold); border-radius: var(--radius-sm); padding: 7px 9px; cursor: pointer; }
.history-item { position: relative; width: 100%; display: grid; gap: 4px; text-align: left; padding: 11px 28px 11px 10px; margin-bottom: 5px; border: 1px solid transparent; border-radius: var(--radius-md); color: var(--text-secondary); background: transparent; cursor: pointer; }
.history-item:hover, .history-item.active { border-color: var(--line); background: var(--surface-muted); }
.history-item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-item small, .muted, .history-empty { color: var(--muted); }
.history-item i { position: absolute; right: 10px; top: 12px; font-style: normal; color: var(--muted); }
.memory-link { display: block; margin-top: 18px; color: var(--gold); }
.memory-suggestions { margin-top: 14px; padding: 12px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); }
.memory-suggestions strong { display: block; margin-bottom: 8px; color: var(--text-secondary); }
.memory-suggestions article { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding-top: 8px; }
.memory-suggestions button { border: 0; border-radius: var(--radius-sm); padding: 7px 10px; color: #24211b; background: var(--gold); cursor: pointer; white-space: nowrap; }
.memory-suggestions button:disabled { opacity: .55; cursor: default; }
.favorite-suggestions { border-color: var(--line-strong); background: rgba(233, 200, 117, .06); }
.favorite-suggestions button { background: var(--gold); }
.related-entities { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
.related-entities a { min-width: 220px; display: grid; grid-template-columns: 40px minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 9px 12px; border: 1px solid var(--line); border-radius: var(--radius-md); color: var(--text); background: var(--surface); text-decoration: none; }
.related-entities a:hover, .related-entities a:focus-visible { border-color: var(--line-strong); background: var(--surface-muted); outline: none; }
.related-entities img { width: 40px; height: 40px; border-radius: 50%; object-fit: cover; background: var(--page-soft); }
.entity-placeholder { display: grid; place-items: center; width: 40px; height: 40px; border: 1px solid var(--line-strong); border-radius: 50%; color: var(--gold); background: var(--surface-muted); font-size: 13px; font-style: normal; }
.related-entities span { min-width: 0; display: grid; gap: 2px; }
.related-entities small { color: var(--muted); }
.related-entities strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .92rem; }
.related-entities b { color: var(--gold); }
.follow-up-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.live-step { margin-top: 6px; padding: 8px 12px; border-left: 2px solid var(--gold); background: var(--surface-muted); border-radius: 0 var(--radius-sm) var(--radius-sm) 0; }
.live-step strong { display: block; font-size: .85rem; color: var(--gold); }
.live-step p { margin: 4px 0 0; font-size: .82rem; color: var(--text-secondary); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.follow-up-chips button { border: 1px dashed var(--line-strong); background: transparent; color: var(--text-muted); border-radius: 999px; padding: 5px 12px; font: inherit; font-size: .85rem; cursor: pointer; }
.follow-up-chips button:hover:not(:disabled) { color: var(--gold); border-color: var(--gold); }
.follow-up-chips button:disabled { opacity: .5; cursor: default; }
.agent-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
.agent-actions button { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border: 1px solid var(--gold); border-radius: var(--radius-md); color: var(--gold); background: transparent; font: inherit; font-size: .92rem; cursor: pointer; }
.agent-actions button:hover, .agent-actions button:focus-visible { background: var(--surface-muted); outline: none; }
@media (max-width: 1080px) {
  .chat-layout { grid-template-columns: 1fr; }
  .history-panel { display: none; }
}

<style scoped>
.process-toggle {
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--text-secondary);
  background: transparent;
  font-size: 10px;
  cursor: pointer;
}
.process-toggle:hover {
  color: var(--gold);
  border-color: var(--gold);
}
</style>
