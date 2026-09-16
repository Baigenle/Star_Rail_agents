<script setup lang="ts">
import axios from 'axios'
import { onMounted, ref } from 'vue'

import AppShell from '../components/AppShell.vue'
import CustomCharacterPreview from '../components/CustomCharacterPreview.vue'
import {
  assessCustomCharacter,
  getCommunityModeration,
  getPendingReviews,
  moderateCommunityCharacter,
  reviewCustomCharacter,
} from '../services/api'
import type { CustomCharacter } from '../types/customCharacter'
import type { AIAssessment, ModerationItem } from '../types/moderation'

type Tab = 'pending' | 'published' | 'unpublished'
const tab = ref<Tab>('pending')
const pending = ref<CustomCharacter[]>([])
const managed = ref<ModerationItem[]>([])
const error = ref('')
const reasons = ref<Record<string, string>>({})
const assessments = ref<Record<string, AIAssessment>>({})
const assessing = ref('')

async function load() {
  error.value = ''
  try {
    if (tab.value === 'pending') {
      pending.value = await getPendingReviews()
    } else {
      managed.value = await getCommunityModeration('character', tab.value)
    }
  } catch (err) {
    error.value = axios.isAxiosError(err)
      ? String(err.response?.data?.detail ?? '无法读取审核列表。')
      : '无法读取审核列表。'
  }
}

async function selectTab(value: Tab) {
  tab.value = value
  await load()
}

async function decide(item: CustomCharacter, action: 'approve' | 'reject') {
  try {
    await reviewCustomCharacter(item.version_id, action, reasons.value[item.version_id])
    await load()
  } catch (err) {
    error.value = axios.isAxiosError(err)
      ? String(err.response?.data?.detail ?? '审核失败。')
      : '审核失败。'
  }
}

async function assess(item: CustomCharacter) {
  assessing.value = item.version_id
  try {
    assessments.value[item.version_id] = await assessCustomCharacter(item.version_id)
  } catch {
    error.value = 'AI辅助审核暂时不可用，仍可继续人工审核。'
  } finally {
    assessing.value = ''
  }
}

async function moderate(item: ModerationItem) {
  const action = tab.value === 'published' ? 'unpublish' : 'republish'
  try {
    await moderateCommunityCharacter(
      item.content_id,
      action,
      reasons.value[item.content_id] || '',
    )
    await load()
  } catch (err) {
    error.value = axios.isAxiosError(err)
      ? String(err.response?.data?.detail ?? '内容管理失败。')
      : '内容管理失败。'
  }
}

onMounted(load)
</script>

<template>
  <AppShell>
    <header>
      <div>
        <span class="eyebrow">MODERATION</span>
        <h1>社区角色审核</h1>
        <p>AI只提供完整性与一致性报告，最终决定始终由管理员作出。</p>
      </div>
    </header>
    <nav class="review-tabs">
      <button :class="{ active: tab === 'pending' }" @click="selectTab('pending')">待审核</button>
      <button :class="{ active: tab === 'published' }" @click="selectTab('published')">已发布</button>
      <button :class="{ active: tab === 'unpublished' }" @click="selectTab('unpublished')">已下架</button>
    </nav>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <section v-if="tab === 'pending'" class="review-list">
      <p v-if="!pending.length" class="catalog-state">当前没有待审核版本。</p>
      <article v-for="item in pending" :key="item.version_id">
        <CustomCharacterPreview :payload="item.payload" :status="`待审核 v${item.version_number}`" />
        <div>
          <h2>{{ item.name }}</h2>
          <p>作者 {{ item.author_name }}</p>
          <button class="assist" :disabled="assessing === item.version_id" @click="assess(item)">
            {{ assessing === item.version_id ? '模型分析中…' : 'AI辅助审核' }}
          </button>
          <div v-if="assessments[item.version_id]" class="assessment">
            <strong>完整度 {{ assessments[item.version_id].completeness.score }}%</strong>
            <small>{{ assessments[item.version_id].model_used ? '规则 + 推理模型' : '确定性规则降级报告' }}</small>
            <p v-for="warning in [
              ...assessments[item.version_id].consistency_warnings,
              ...assessments[item.version_id].numerical_risks,
              ...assessments[item.version_id].official_lore_risks,
              ...assessments[item.version_id].suggestions,
            ]" :key="warning">{{ warning }}</p>
            <p v-if="!assessments[item.version_id].completeness.passed">
              缺少：{{ assessments[item.version_id].completeness.missing_fields.join('、') }}
            </p>
          </div>
          <textarea v-model="reasons[item.version_id]" rows="4" placeholder="驳回时必须填写理由；通过时可选。" />
          <div class="actions">
            <button @click="decide(item, 'approve')">通过并公开</button>
            <button @click="decide(item, 'reject')">驳回</button>
          </div>
        </div>
      </article>
    </section>

    <section v-else class="managed-list">
      <p v-if="!managed.length" class="catalog-state">当前没有对应内容。</p>
      <article v-for="item in managed" :key="item.content_id">
        <div><span>{{ tab === 'published' ? '已发布' : '已下架' }}</span><h2>{{ item.title }}</h2><p>作者 {{ item.author_name }}</p><small v-if="item.reason">原因：{{ item.reason }}</small></div>
        <textarea v-if="tab === 'published'" v-model="reasons[item.content_id]" rows="2" placeholder="下架原因（必填）" />
        <button @click="moderate(item)">{{ tab === 'published' ? '下架角色' : '恢复上架' }}</button>
      </article>
    </section>
  </AppShell>
</template>

<style scoped>
header p, article p { color: var(--muted); }
.review-tabs { display: flex; gap: 8px; margin: 18px 0; }
.review-tabs button { border: 1px solid var(--line); border-radius: 999px; padding: 9px 15px; background: transparent; cursor: pointer; }
.review-tabs button.active { border-color: var(--gold); color: var(--gold); background: rgba(230, 201, 130, .1); }
.review-list { display: grid; gap: 1rem; }
.review-list article { display: grid; grid-template-columns: 280px 1fr; gap: 1rem; padding: 1rem; border: 1px solid var(--line); background: var(--panel); }
textarea { box-sizing: border-box; width: 100%; margin-top: 10px; border: 1px solid var(--line); padding: .75rem; color: inherit; background: #0b1122; }
.actions { display: flex; gap: .75rem; margin-top: .75rem; }
button { border: 1px solid var(--gold); padding: .7rem 1rem; background: transparent; cursor: pointer; }
.assist { margin-bottom: 8px; border-color: #a983ff; color: #cbb6ff; }
.assessment { margin: 8px 0; padding: 12px; border: 1px solid rgba(169, 131, 255, .35); border-radius: 10px; background: rgba(94, 62, 160, .12); }
.assessment strong, .assessment small { display: block; }
.assessment small { margin: 4px 0 8px; color: var(--muted); }
.assessment p { margin: 5px 0; font-size: 12px; }
.managed-list { display: grid; gap: 10px; }
.managed-list article { display: grid; grid-template-columns: 1fr 1fr auto; gap: 14px; align-items: center; padding: 18px; border: 1px solid var(--line); background: var(--panel); }
.managed-list span { color: var(--gold); font-size: 10px; }
.managed-list h2 { margin: 6px 0; }
@media (max-width: 760px) { .review-list article, .managed-list article { grid-template-columns: 1fr; } }
</style>
