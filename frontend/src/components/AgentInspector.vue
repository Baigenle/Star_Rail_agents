<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'

import { useChatTaskStore } from '../stores/chatTasks'
import { useUiStore } from '../stores/ui'
import type { AIResponse } from '../types/ai'

const props = defineProps<{
  conversationId?: string
  fallbackResponse?: AIResponse | null
}>()

const tasks = useChatTaskStore()
const ui = useUiStore()

const agentLabels: Record<string, string> = {
  fc_main_agent: '黑塔 · 主控大脑',
  react_main_agent: '黑塔 · 主 Agent',
  herta_main_agent: '黑塔主 Agent',
  router_agent: 'Router Agent',
  rag_agent: 'RAG Agent',
  story_analysis_agent: '剧情解析 Agent',
  team_recommendation_agent: '智能配队 Agent',
  character_build_agent: '角色养成 Agent',
  material_query_agent: '材料查询 Agent',
  activity_strategy_agent: '活动攻略 Agent',
  memory_agent: '长期记忆 Agent',
  weekly_planning_agent: '每周规划 Agent',
  custom_character_agent: '角色创作 Agent',
  conversation_agent: '对话理解 Agent',
  knowledge_search: '知识库检索',
  catalog_search: '角色目录检索',
  character_profile: '角色档案查询',
  character_materials: '养成材料对齐',
  character_build: '养成建议引擎',
  team_recommendation: '智能配队引擎',
  activity_strategy: '活动攻略助手',
  weekly_planning: '每周规划助手',
  custom_character_guide: '创作工坊引导',
  custom_character_review: '原创角色自查',
}

// answer.delta 是逐字流本身（展示在对话区），不进过程时间线刷屏
const hiddenEventTypes = new Set(['answer.delta'])

const visibleEvents = computed(() =>
  events.value.filter((event) => !hiddenEventTypes.has(event.event_type)),
)

const currentJob = computed(() => {
  const jobs = Object.values(tasks.jobs)
    .filter((job) => !props.conversationId || job.conversation_id === props.conversationId)
    .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime())
  return jobs.find((job) => job.status === 'queued' || job.status === 'running') ?? jobs[0]
})
const events = computed(() => currentJob.value ? tasks.events[currentJob.value.id] ?? [] : [])
const response = computed(() => currentJob.value?.response ?? props.fallbackResponse ?? null)
const percent = computed(() => currentJob.value?.progress?.percent ?? (response.value ? 100 : 0))
const currentAgent = computed(() => {
  const name = currentJob.value?.progress?.agent
  return name ? agentLabels[name] ?? name : '等待任务'
})
const invokedAgents = computed(() => {
  const names = response.value?.invoked_agents
    ?? [...events.value].reverse().find((event) => event.payload.invoked_agents)?.payload.invoked_agents
    ?? []
  return [...new Set(names)]
})

function eventAgent(name?: string | null) {
  return name ? agentLabels[name] ?? name : '系统'
}

function onEscape(event: KeyboardEvent) {
  if (event.key === 'Escape' && ui.inspectorOpen) ui.closeInspector()
}

onMounted(() => window.addEventListener('keydown', onEscape))
onBeforeUnmount(() => window.removeEventListener('keydown', onEscape))
</script>

<template>
  <div class="inspector-content">
    <header class="inspector-header">
      <div>
        <span class="eyebrow">AGENT INSPECTOR</span>
        <h2>执行过程</h2>
      </div>
      <button type="button" aria-label="关闭 Agent 执行面板" @click.stop="ui.closeInspector()">×</button>
    </header>

    <section class="progress-card" aria-live="polite">
      <div>
        <span>{{ currentAgent }}</span>
        <strong>{{ percent }}%</strong>
      </div>
      <progress :value="percent" max="100">{{ percent }}%</progress>
      <small>
        {{
          currentJob?.status === 'failed'
            ? '任务执行失败，可返回对话页重试。'
            : currentJob?.status === 'completed'
              ? '全部 Agent 阶段已完成。'
              : '仅展示可审计执行阶段，不展示模型私有推理链。'
        }}
      </small>
    </section>

    <section v-if="invokedAgents.length" class="inspector-section">
      <h3>本轮调用</h3>
      <div class="invoked-agent-list">
        <span v-for="name in invokedAgents" :key="name">
          {{ agentLabels[name] ?? name }}
        </span>
      </div>
    </section>

    <section class="inspector-section">
      <h3>实时轨迹</h3>
      <ol v-if="visibleEvents.length" class="event-timeline">
        <li v-for="event in visibleEvents" :key="event.sequence" :class="event.status">
          <i aria-hidden="true" />
          <div>
            <span>{{ event.title }}</span>
            <small>{{ eventAgent(event.agent) }}</small>
            <p v-if="event.detail">{{ event.detail }}</p>
          </div>
          <time>{{ event.duration_ms != null ? `${event.duration_ms} ms` : `#${event.sequence}` }}</time>
        </li>
      </ol>
      <p v-else class="inspector-empty">发送问题后，这里会实时显示黑塔的思考轮次、工具调用与后台任务汇报。</p>
    </section>

    <template v-if="response">
      <section class="inspector-section protocol-section">
        <h3>Claim <small>主张</small></h3>
        <article v-for="claim in response.claims" :key="claim.statement">
          <p>{{ claim.statement }}</p>
          <small>置信度 {{ Math.round(claim.confidence * 100) }}% · {{ claim.citation_ids.join(', ') || '无引用' }}</small>
        </article>
        <p v-if="!response.claims.length" class="inspector-empty">本轮没有形成可独立验证的事实主张。</p>
      </section>

      <section class="inspector-section protocol-section">
        <h3>Citation <small>引用</small></h3>
        <article v-for="citation in response.citations" :key="citation.id">
          <b>{{ citation.id }}</b>
          <span>{{ citation.title }}</span>
          <router-link v-if="citation.entity_url" :to="citation.entity_url">查看档案 →</router-link>
        </article>
      </section>

      <section class="inspector-section protocol-section">
        <h3>Validation <small>验证</small></h3>
        <p>{{ response.validation.notes.join(' ') || response.validation.method }}</p>
      </section>

      <section class="inspector-section protocol-section">
        <h3>Filtering <small>过滤</small></h3>
        <p>{{ [...response.filtering.rules, ...response.filtering.warnings].join(' ') || '未发现需要过滤的低可信内容。' }}</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.inspector-content { display: grid; gap: 18px; padding: 20px; }
.inspector-header { position: sticky; z-index: 2; top: 0; align-items: center; margin: -20px -20px 0; padding: 18px 20px; border-bottom: 1px solid var(--line); background: color-mix(in srgb, var(--page-soft) 94%, transparent); backdrop-filter: blur(16px); }
.inspector-header h2 { margin: 4px 0 0; font-size: 20px; }
.inspector-header button { position: relative; z-index: 3; width: 34px; height: 34px; border: 1px solid var(--line); border-radius: var(--radius-sm); color: var(--muted); background: var(--surface); cursor: pointer; touch-action: manipulation; }
.progress-card, .inspector-section { padding: 16px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); }
.progress-card > div { display: flex; justify-content: space-between; gap: 12px; }
.progress-card span { color: var(--text-secondary); font-size: 12px; }
.progress-card strong { color: var(--gold); }
.progress-card progress { width: 100%; height: 5px; margin: 14px 0 10px; accent-color: var(--gold); }
.progress-card small, .inspector-empty { color: var(--muted); font-size: 10px; line-height: 1.65; }
.inspector-section h3 { margin: 0 0 13px; font-family: Georgia, "Times New Roman", serif; font-size: 13px; letter-spacing: .06em; }
.inspector-section h3 small { margin-left: 5px; color: var(--muted); font-family: inherit; font-weight: 400; }
.invoked-agent-list { display: flex; flex-wrap: wrap; gap: 6px; }
.invoked-agent-list span { padding: 5px 8px; border: 1px solid var(--line); border-radius: 999px; color: var(--text-secondary); font-size: 9px; }
.event-timeline { display: grid; gap: 0; margin: 0; padding: 0; list-style: none; }
.event-timeline li { position: relative; display: grid; grid-template-columns: 12px minmax(0, 1fr) auto; gap: 9px; padding: 0 0 16px; }
.event-timeline li:not(:last-child)::after { content: ""; position: absolute; top: 12px; bottom: 0; left: 4px; width: 1px; background: var(--line); }
.event-timeline i { position: relative; z-index: 1; width: 9px; height: 9px; margin-top: 3px; border: 2px solid var(--page-soft); border-radius: 50%; background: var(--gold); }
.event-timeline li.failed i { background: var(--danger); }
.event-timeline span { display: block; color: var(--text-secondary); font-size: 11px; }
.event-timeline small, .event-timeline time { color: var(--muted); font-size: 8px; }
.event-timeline p { margin: 6px 0 0; color: var(--muted); font-size: 10px; line-height: 1.6; }
.protocol-section article { padding: 10px 0; border-top: 1px solid var(--line); }
.protocol-section article p, .protocol-section > p { margin: 0; color: var(--text-secondary); font-size: 11px; line-height: 1.7; }
.protocol-section article small { color: var(--muted); font-size: 9px; }
.protocol-section article b { margin-right: 7px; color: var(--gold); font-size: 9px; }
.protocol-section article span { color: var(--text-secondary); font-size: 11px; }
.protocol-section article a { display: block; margin-top: 6px; color: var(--gold); font-size: 9px; text-decoration: none; }
</style>
