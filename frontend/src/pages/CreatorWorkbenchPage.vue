<script setup lang="ts">
import axios from 'axios'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import CreatorStageForm from '../components/CreatorStageForm.vue'
import CustomCharacterPreview from '../components/CustomCharacterPreview.vue'
import SelfReviewPanel from '../components/SelfReviewPanel.vue'
import {
  confirmCreatorStage,
  createCreatorSession,
  getCustomCharacter,
  getCustomCharacterSelfReview,
  getLatestCreatorSession,
  recommendCustomTeams,
  sendCreatorMessage,
  runCustomCharacterSelfReview,
  submitCustomCharacter,
  updateCustomCharacter,
} from '../services/api'
import type { CreatorSession, CustomCharacter, CustomTeamResult, SelfReviewReport } from '../types/customCharacter'
import { cloneReactivePayload } from '../utils/cloneReactivePayload'
import { getCustomCharacterWorkflowNotice } from '../utils/customCharacterWorkflowNotice'

const route = useRoute()
const character = ref<CustomCharacter | null>(null)
const session = ref<CreatorSession | null>(null)
const pending = ref(false)
const busy = ref(false)
const message = ref('我是黑塔。四个阶段逐项确认，没说清楚的数值我不会替你编。')
const error = ref('')
const teamResult = ref<CustomTeamResult | null>(null)
const selfReview = ref<SelfReviewReport | null>(null)
const editingStage = ref<number | null>(null)

const fieldStages: Record<string, number> = {
  name: 1, rarity: 1, element: 1, path: 1, summary: 1,
  roles: 2, core_mechanics: 2, mechanic_tags: 2,
  base_stats: 3, skills: 3,
  special_skills: 4, story: 4, eidolons: 4,
}

const canSubmit = computed(() => Boolean(
  selfReview.value
  && selfReview.value.overall_score >= 60
  && selfReview.value.must_fix_count === 0,
))
const workflowNotice = computed(() => character.value
  ? getCustomCharacterWorkflowNotice(character.value.status, character.value.review_reason)
  : null)
const stageStatuses = computed(() => [1, 2, 3, 4].map((stage) => {
  const payload = character.value?.payload
  if (!payload) return { stage, status: 'error', label: '未填写' }
  const complete = stage === 1
    ? Boolean(payload.name && payload.rarity && payload.element && payload.path && payload.summary)
    : stage === 2
      ? Boolean(payload.roles?.length && payload.core_mechanics)
      : stage === 3
        ? Boolean(payload.base_stats && ['basic', 'skill', 'ultimate', 'talent', 'technique'].every((key) => payload.skills?.[key]))
        : payload.path === '记忆'
          ? Boolean(payload.special_skills?.memosprite_skill && payload.special_skills?.memosprite_talent)
          : payload.path === '欢愉'
            ? Boolean(payload.special_skills?.elation_skill)
            : true
  const issues = selfReview.value?.categories.flatMap((category) => category.issues)
    .filter((issue) => stageForField(issue.field) === stage) ?? []
  if (!complete || issues.some((issue) => issue.severity === 'error')) return { stage, status: 'error', label: '需要修改' }
  if (issues.length || (stage === 4 && !payload.story && !payload.eidolons?.length)) return { stage, status: 'warning', label: '可以优化' }
  return { stage, status: 'ready', label: '已完成' }
}))

async function load() {
  busy.value = true
  try {
    character.value = await getCustomCharacter(String(route.params.id))
    try {
      session.value = await getLatestCreatorSession(character.value.id)
      message.value = session.value.status === 'completed'
        ? '我是黑塔。这个角色档案已经完成，可以继续生成配队或提交审核。'
        : `我是黑塔。已恢复到第 ${session.value.stage} 阶段，继续把这一阶段的资料告诉我。`
    } catch (err) {
      if (!axios.isAxiosError(err) || err.response?.status !== 404) throw err
      session.value = await createCreatorSession(character.value.id)
    }
    try {
      selfReview.value = await getCustomCharacterSelfReview(character.value.id)
    } catch (err) {
      if (!axios.isAxiosError(err) || err.response?.status !== 404) throw err
    }
  } catch (err) {
    error.value = axios.isAxiosError(err) ? String(err.response?.data?.detail ?? '创作工坊载入失败。') : '创作工坊载入失败。'
  } finally { busy.value = false }
}

async function sendStage(userMessage: string, fields: Record<string, unknown>) {
  if (!session.value) return
  busy.value = true
  error.value = ''
  try {
    const turn = await sendCreatorMessage(session.value.id, userMessage, fields)
    message.value = turn.response.answer
    pending.value = true
  } catch (err) {
    error.value = axios.isAxiosError(err) ? String(err.response?.data?.detail ?? '字段检查失败。') : '字段检查失败。'
  } finally { busy.value = false }
}

async function confirm() {
  if (!session.value || !character.value) return
  busy.value = true
  error.value = ''
  try {
    const turn = await confirmCreatorStage(session.value.id)
    session.value.stage = turn.stage
    session.value.status = turn.stage === 4 && turn.response.answer.includes('四个阶段') ? 'completed' : session.value.status
    character.value.payload = turn.draft
    message.value = turn.response.answer
    pending.value = false
    if (turn.response.answer.includes('四个阶段')) session.value.status = 'completed'
  } catch (err) {
    error.value = axios.isAxiosError(err) ? String(err.response?.data?.detail ?? '阶段确认失败。') : '阶段确认失败。'
  } finally { busy.value = false }
}

async function buildTeams() {
  if (!character.value) return
  busy.value = true
  try { teamResult.value = await recommendCustomTeams(character.value.id) }
  catch (err) { error.value = axios.isAxiosError(err) ? String(err.response?.data?.detail ?? '配队生成失败。') : '配队生成失败。' }
  finally { busy.value = false }
}

async function runSelfReview() {
  if (!character.value) return
  busy.value = true
  error.value = ''
  try {
    selfReview.value = await runCustomCharacterSelfReview(character.value.id)
    message.value = selfReview.value.verdict === 'ready'
      ? '自助审核完成。已经达到提交条件，剩余建议由你决定是否继续优化。'
      : '自助审核完成。我把问题按阶段标好了，先处理红色必须修复项。'
  } catch (err) {
    error.value = axios.isAxiosError(err) ? String(err.response?.data?.detail ?? '自助审核失败。') : '自助审核失败。'
  } finally { busy.value = false }
}

function stageForField(field: string): number {
  const root = field.split('.')[0]
  return fieldStages[root] ?? 1
}

async function editIssue(field: string) {
  editingStage.value = stageForField(field)
  await nextTick()
  const fallback = field === 'base_stats' ? 'base_stats-speed' : field === 'skills' ? 'skills-skill' : field
  const target = document.getElementById(`creator-${fallback.replaceAll('.', '-')}`)
  target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  target?.focus()
}

async function saveStageEdit(_message: string, fields: Record<string, unknown>) {
  if (!character.value) return
  busy.value = true
  error.value = ''
  try {
    const payload = cloneReactivePayload(character.value.payload)
    Object.assign(payload, fields)
    character.value = await updateCustomCharacter(character.value.id, payload)
    selfReview.value = null
    editingStage.value = null
    message.value = '修改已经写入私有草稿，旧审核报告已失效。重新运行自助审核后再提交。'
  } catch (err) {
    if (axios.isAxiosError(err)) {
      error.value = String(err.response?.data?.detail ?? '保存修改失败。')
    } else if (err instanceof Error) {
      error.value = `保存修改失败：${err.message}`
    } else {
      error.value = '保存修改失败。'
    }
  } finally { busy.value = false }
}

async function submitReview() {
  if (!character.value) return
  if (!canSubmit.value) {
    error.value = '请先完成自助审核并处理全部必须修复项。'
    return
  }
  busy.value = true
  try {
    character.value = await submitCustomCharacter(character.value.id)
    message.value = '已提交社区审核。审核结果和驳回原因会保留在作品状态中；旧公开版本不会因为这次提交而下线。'
  } catch (err) { error.value = axios.isAxiosError(err) ? String(err.response?.data?.detail ?? '提交失败。') : '提交失败。' }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <p v-if="busy && !character" class="catalog-state">黑塔正在打开创作档案…</p>
    <div v-else-if="error && !character" class="catalog-state">{{ error }}</div>
    <template v-else-if="character && session">
      <nav class="breadcrumbs"><router-link to="/creator">创作工坊</router-link><span>/</span><b>{{ character.name }}</b></nav>
      <section class="workbench">
        <div class="dialogue-panel">
          <span class="eyebrow">STAGE {{ session.stage }} / 4</span>
          <h1>与黑塔共同创作</h1>
          <nav class="stage-status" aria-label="创作阶段状态">
            <button v-for="item in stageStatuses" :key="item.stage" type="button" :data-status="item.status" :disabled="session.status !== 'completed'" @click="editingStage = item.stage">
              <span>阶段 {{ item.stage }}</span><small>{{ item.label }}</small>
            </button>
          </nav>
          <div class="herta-message"><b>H</b><p>{{ message }}</p></div>
          <section
            v-if="workflowNotice"
            class="workflow-notice"
            :data-tone="workflowNotice.tone"
            role="status"
          >
            <div>
              <span class="eyebrow">REVIEW STATUS</span>
              <h2>{{ workflowNotice.title }}</h2>
            </div>
            <p>{{ workflowNotice.description }}</p>
          </section>
          <CreatorStageForm v-if="session.status === 'active'" :stage="session.stage" :draft="character.payload" :disabled="busy || pending" @submit="sendStage" />
          <button v-if="pending" class="confirm-button" :disabled="busy" @click="confirm">确认本阶段并写入草稿</button>
          <section v-if="session.status === 'completed' && editingStage" class="stage-editor">
            <header><div><span class="eyebrow">EDIT STAGE {{ editingStage }}</span><h2>修改已确认内容</h2></div><button type="button" @click="editingStage = null">取消修改</button></header>
            <CreatorStageForm :stage="editingStage" :draft="character.payload" :disabled="busy" submit-label="保存修改并重新审核" @submit="saveStageEdit" />
          </section>
          <div v-if="session.status === 'completed' && !editingStage" class="finish-actions"><button :disabled="busy || character.status !== 'draft'" @click="runSelfReview">{{ selfReview ? '重新运行自助审核' : '运行玩家自助审核' }}</button><button :disabled="busy" @click="buildTeams">生成配队方案</button></div>
          <SelfReviewPanel v-if="selfReview" :report="selfReview" @edit="editIssue" />
          <section v-if="session.status === 'completed' && character.status === 'draft'" class="submit-checklist">
            <h2>提交前确认</h2>
            <ul>
              <li :data-done="stageStatuses.every((item) => item.status !== 'error')">四个阶段的必填字段已经完成</li>
              <li :data-done="Boolean(selfReview)">已运行当前草稿的玩家自助审核</li>
              <li :data-done="Boolean(selfReview && selfReview.must_fix_count === 0)">不存在红色必须修复项</li>
              <li :data-done="Boolean(selfReview && selfReview.overall_score >= 60)">审核总分达到 60 分</li>
            </ul>
            <p v-if="selfReview?.warn_count">仍有 {{ selfReview.warn_count }} 条黄色建议；这些建议可以继续修改，也可以确认后提交。</p>
            <button type="button" :disabled="busy || !canSubmit" @click="submitReview">{{ selfReview?.warn_count ? '确认建议并提交社区审核' : '提交社区审核' }}</button>
          </section>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <section v-if="teamResult" class="team-results">
            <h2>理论配队</h2>
            <article v-for="team in teamResult.theoretical" :key="team.members.map((m) => m.character_id).join('-')"><b>{{ team.score }} 分</b><h3>{{ team.members.map((member) => member.name).join(' · ') }}</h3><p>{{ team.reasons.join('；') }}</p></article>
            <h2>我的替代</h2>
            <article v-for="team in teamResult.owned" :key="`owned-${team.members.map((m) => m.character_id).join('-')}`"><b>{{ team.score }} 分</b><h3>{{ team.members.map((member) => member.name).join(' · ') }}</h3></article>
            <details><summary>Claim → Citation → Validation → Filtering</summary><pre>{{ JSON.stringify(teamResult.response, null, 2) }}</pre></details>
          </section>
        </div>
        <CustomCharacterPreview :payload="character.payload" :status="character.status" />
      </section>
    </template>
  </AppShell>
</template>

<style scoped>
.workbench { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(280px, .75fr); gap: 1.25rem; align-items: start; }
.dialogue-panel { min-width: 0; }
.herta-message { display: flex; gap: .8rem; margin: 1rem 0; padding: 1rem; border: 1px solid var(--line); background: var(--panel); }
.herta-message b { display: grid; place-items: center; flex: 0 0 2.5rem; height: 2.5rem; border: 1px solid var(--gold); border-radius: 50%; color: var(--gold); }
.herta-message p { margin: 0; line-height: 1.8; }
.workflow-notice { display: grid; grid-template-columns: minmax(11rem, .35fr) minmax(0, 1fr); gap: 1rem; margin: 1rem 0; padding: 1rem; border: 1px solid var(--line); border-left: .25rem solid var(--gold); background: var(--panel); }
.workflow-notice h2, .workflow-notice p { margin: 0; }
.workflow-notice h2 { margin-top: .25rem; font-size: 1.05rem; }
.workflow-notice p { color: var(--text-secondary); line-height: 1.75; }
.workflow-notice[data-tone="success"] { border-left-color: var(--success); }
.workflow-notice[data-tone="warning"] { border-left-color: var(--danger); }
.confirm-button, .finish-actions button { width: 100%; margin-top: .75rem; border: 1px solid var(--gold); padding: .8rem; background: rgba(230,201,130,.12); cursor: pointer; }
.finish-actions { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; }
.stage-status { display: grid; grid-template-columns: repeat(4, 1fr); gap: .5rem; margin: 1rem 0; }
.stage-status button { display: grid; gap: .2rem; padding: .65rem; border: 1px solid var(--line); color: var(--text-secondary); background: var(--surface-raised); text-align: left; cursor: pointer; }
.stage-status button[data-status="ready"] { border-bottom-color: var(--success); }
.stage-status button[data-status="warning"] { border-bottom-color: var(--gold); }
.stage-status button[data-status="error"] { border-bottom-color: var(--danger); }
.stage-status small { color: var(--muted); }
.stage-editor { display: grid; gap: .75rem; margin-top: 1rem; }
.stage-editor > header { display: flex; justify-content: space-between; align-items: end; margin: 0; }
.stage-editor h2 { margin: .2rem 0 0; }
.stage-editor > header button { border: 1px solid var(--line); padding: .55rem .75rem; color: var(--text); background: transparent; cursor: pointer; }
.submit-checklist { display: grid; gap: .75rem; margin-top: 1rem; padding: 1rem; border: 1px solid var(--line); background: var(--panel); }
.submit-checklist h2, .submit-checklist p { margin: 0; }
.submit-checklist ul { display: grid; gap: .45rem; margin: 0; padding: 0; list-style: none; }
.submit-checklist li::before { content: '○'; margin-right: .5rem; color: var(--danger); }
.submit-checklist li[data-done="true"]::before { content: '✓'; color: var(--success); }
.submit-checklist p { color: var(--text-secondary); }
.submit-checklist button { border: 1px solid var(--gold); padding: .8rem; color: var(--text); background: color-mix(in srgb, var(--gold) 12%, var(--surface)); cursor: pointer; }
.submit-checklist button:disabled, .finish-actions button:disabled { cursor: not-allowed; opacity: .5; }
.team-results { display: grid; gap: .75rem; margin-top: 1.5rem; }
.team-results article { padding: 1rem; border: 1px solid var(--line); background: var(--panel); }
.team-results article > b { color: var(--gold); }
.team-results h3, .team-results p { margin: .35rem 0; }
.team-results p { color: var(--muted); }
pre { max-height: 24rem; overflow: auto; white-space: pre-wrap; color: #aebbd8; }
@media (max-width: 900px) { .workbench { grid-template-columns: 1fr; } }
@media (max-width: 620px) { .stage-status, .finish-actions { grid-template-columns: 1fr 1fr; } .workflow-notice { grid-template-columns: 1fr; } }
</style>
