<script setup lang="ts">
import { onMounted, ref } from 'vue'

import AppShell from '../components/AppShell.vue'
import {
  deleteMemory,
  getCharacterPool,
  getMemories,
  getProgressionPlans,
  getSavedTeams,
  updateMemory,
} from '../services/api'
import type { MemoryRecord } from '../types/ai'

const items = ref<MemoryRecord[]>([])
const loading = ref(true)
const error = ref('')
const editingId = ref('')
const editContent = ref('')
const deletingId = ref('')
const operationMessage = ref('')
const operationError = ref('')
const profileFacts = ref({ owned: 0, favorites: 0, teams: 0, plans: 0 })

const labels: Record<MemoryRecord['memory_type'], string> = {
  playstyle_preference: '玩法偏好',
  resource_priority: '资源优先级',
  favorite_character: '喜欢角色',
  usual_team: '常用队伍',
  answer_preference: '回答偏好',
}
const effects: Record<MemoryRecord['memory_type'], string> = {
  playstyle_preference: '影响意图理解、配队解释和玩法建议',
  resource_priority: '影响养成顺序与每周体力安排',
  favorite_character: '用于生成额外的“猜你喜欢”方案，不修改最优配队评分',
  usual_team: '影响队伍替代建议和常用组合说明',
  answer_preference: '只改变回答表达方式，不改变知识事实',
}

async function load() {
  loading.value = true
  try {
    const [memories, pool, teams, plans] = await Promise.all([
      getMemories(),
      getCharacterPool(),
      getSavedTeams(),
      getProgressionPlans(),
    ])
    items.value = memories
    profileFacts.value = {
      owned: pool.items.length,
      favorites: pool.favorites,
      teams: teams.length,
      plans: plans.filter((item) => item.status === 'active').length,
    }
  } catch {
    error.value = '长期记忆读取失败。'
  } finally {
    loading.value = false
  }
}

function startEdit(item: MemoryRecord) {
  editingId.value = item.id
  editContent.value = item.content
}

async function saveEdit(item: MemoryRecord) {
  const content = editContent.value.trim()
  if (!content) return
  const updated = await updateMemory(item.id, { content })
  items.value = items.value.map((entry) => (entry.id === item.id ? updated : entry))
  editingId.value = ''
}

async function toggle(item: MemoryRecord) {
  const updated = await updateMemory(item.id, { is_active: !item.is_active })
  items.value = items.value.map((entry) => (entry.id === item.id ? updated : entry))
}

async function remove(item: MemoryRecord) {
  if (!window.confirm(`确定永久删除这条${labels[item.memory_type]}吗？删除后不会再影响黑塔的回答。`)) {
    return
  }
  deletingId.value = item.id
  operationMessage.value = ''
  operationError.value = ''
  try {
    await deleteMemory(item.id)
    items.value = items.value.filter((entry) => entry.id !== item.id)
    operationMessage.value = '长期记忆已删除，后续 Agent 不会再读取这条偏好。'
  } catch {
    operationError.value = '删除失败，记忆仍然保留。请检查登录状态或后端服务。'
  } finally {
    deletingId.value = ''
  }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <header class="page-head">
      <div>
        <span class="eyebrow">CONFIRMED MEMORY</span>
        <h1>长期记忆管理</h1>
        <p>长期记忆保存你的稳定偏好，不保存游戏知识。只有启用的记忆才会进入黑塔与意图识别 Agent 的上下文。</p>
      </div>
      <router-link class="primary-link" to="/">返回与黑塔对话</router-link>
    </header>

    <section class="memory-explainer">
      <article>
        <span>可靠账户资料</span>
        <h2>由功能操作直接维护</h2>
        <p>角色池、喜欢角色、练度、队伍和养成计划不需要再次确认成记忆。</p>
        <div><b>{{ profileFacts.owned }}</b> 拥有角色 · <b>{{ profileFacts.favorites }}</b> 喜欢 · <b>{{ profileFacts.teams }}</b> 队伍 · <b>{{ profileFacts.plans }}</b> 进行中计划</div>
      </article>
      <article>
        <span>用户确认的长期偏好</span>
        <h2>决定黑塔如何理解你</h2>
        <p>玩法、资源优先级和回答方式必须由你确认；停用后会立即从所有 Agent 上下文移除。</p>
      </article>
    </section>

    <p v-if="operationMessage" class="operation-message" role="status">{{ operationMessage }}</p>
    <p v-if="operationError" class="error" role="alert">{{ operationError }}</p>
    <p v-if="loading" class="state-card">正在读取记忆…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <section v-else class="memory-grid">
      <article v-for="item in items" :key="item.id" :class="{ inactive: !item.is_active }">
        <div class="memory-card-head">
          <span>{{ labels[item.memory_type] }}</span>
          <em>{{ item.is_active ? '使用中' : '已停用' }}</em>
        </div>
        <textarea
          v-if="editingId === item.id"
          v-model="editContent"
          rows="3"
          aria-label="编辑记忆内容"
        />
        <p v-else>{{ item.content }}</p>
        <div class="memory-effect"><b>影响范围</b>{{ effects[item.memory_type] }}</div>
        <small>来源：用户确认 · {{ new Date(item.updated_at).toLocaleString() }}</small>
        <div class="memory-actions">
          <template v-if="editingId === item.id">
            <button type="button" @click="saveEdit(item)">保存修改</button>
            <button type="button" class="ghost" @click="editingId = ''">取消</button>
          </template>
          <template v-else>
            <button type="button" @click="startEdit(item)">修改</button>
            <button type="button" class="ghost" @click="toggle(item)">
              {{ item.is_active ? '停用' : '启用' }}
            </button>
            <button
              type="button"
              class="danger"
              :disabled="deletingId === item.id"
              :aria-label="`永久删除${labels[item.memory_type]}`"
              @click="remove(item)"
            >
              {{ deletingId === item.id ? '删除中…' : '永久删除' }}
            </button>
          </template>
        </div>
      </article>
      <div v-if="!items.length" class="state-card">
        还没有确认过长期偏好。你可以在对话中告诉黑塔“我偏好自动战斗”或“养成资源优先给主C”，再确认对应建议。
      </div>
    </section>
  </AppShell>
</template>

<style scoped>
.page-head { display: flex; justify-content: space-between; gap: 20px; align-items: end; margin-bottom: 28px; }
.page-head h1 { margin: 5px 0; }
.page-head p { color: #9690aa; }
.primary-link { padding: 11px 16px; border-radius: 999px; background: #a87df0; color: #100b1a; font-weight: 700; }
.memory-explainer { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 18px; }
.memory-explainer article { padding: 20px; border: 1px solid rgba(177, 137, 255, .25); border-radius: 16px; background: linear-gradient(135deg, rgba(64, 43, 109, .2), rgba(13, 10, 29, .78)); }
.memory-explainer span { color: #c7adff; font-size: 12px; }
.memory-explainer h2 { margin: 8px 0; font-size: 18px; }
.memory-explainer p, .memory-explainer div { color: #9189a3; line-height: 1.7; }
.memory-explainer b { color: #dbcaff; }
.memory-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.memory-grid article, .state-card { padding: 20px; border: 1px solid rgba(177, 137, 255, .25); border-radius: 16px; background: rgba(13, 10, 29, .78); }
.memory-grid article.inactive { opacity: .62; }
.memory-card-head { display: flex; justify-content: space-between; align-items: center; }
.memory-card-head span { color: #c7adff; font-weight: 700; }
.memory-card-head em { font-size: .75rem; font-style: normal; color: #837b99; }
.memory-grid p { min-height: 52px; line-height: 1.7; }
.memory-grid small { color: #777088; }
.memory-effect { margin: 12px 0; padding: 10px; border-left: 2px solid #a87df0; color: #9c93af; background: rgba(168, 125, 240, .07); font-size: 12px; }
.memory-effect b { display: block; margin-bottom: 4px; color: #c7adff; }
textarea { width: 100%; box-sizing: border-box; margin: 12px 0; padding: 11px; border: 1px solid #443761; border-radius: 10px; color: #eee9fa; background: #0b0817; resize: vertical; }
.memory-actions { display: flex; gap: 8px; margin-top: 16px; }
.memory-actions button { padding: 8px 12px; border: 0; border-radius: 9px; background: #a87df0; color: #110c1c; cursor: pointer; }
.memory-actions button:disabled { opacity: .55; cursor: wait; }
.memory-actions .ghost { color: #c8b9e4; background: #282039; }
.memory-actions .danger { color: #ffb2b2; background: #3e202a; }
.operation-message { margin: 0 0 16px; padding: 11px 14px; border: 1px solid rgba(99, 211, 160, .28); border-radius: 10px; color: #a8e4c9; background: rgba(40, 112, 84, .12); }
@media (max-width: 760px) { .memory-explainer { grid-template-columns: 1fr; } }
</style>
