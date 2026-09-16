<script setup lang="ts">
import { onMounted, ref } from 'vue'

import AppShell from '../components/AppShell.vue'
import {
  getCommunityModeration,
  getPendingActivityGuides,
  moderateActivityGuide,
  reviewActivityGuide,
} from '../services/api'
import type { ActivityGuide } from '../types/activity'
import type { ModerationItem } from '../types/moderation'

type Tab = 'pending' | 'published' | 'unpublished'
const tab = ref<Tab>('pending')
const items = ref<ActivityGuide[]>([])
const managed = ref<ModerationItem[]>([])
const reasons = ref<Record<string, string>>({})
const error = ref('')

async function load() {
  error.value = ''
  try {
    if (tab.value === 'pending') items.value = await getPendingActivityGuides()
    else managed.value = await getCommunityModeration('activity_guide', tab.value)
  } catch {
    error.value = '只有 ADMIN_USERNAMES 中的管理员可以管理活动攻略。'
  }
}
async function selectTab(value: Tab) { tab.value = value; await load() }
async function decide(id: string, action: 'approve' | 'reject') {
  try { await reviewActivityGuide(id, action, reasons.value[id]); await load() }
  catch { error.value = action === 'reject' ? '驳回时必须填写理由。' : '审核失败。' }
}
async function moderate(item: ModerationItem) {
  try {
    await moderateActivityGuide(
      item.content_id,
      tab.value === 'published' ? 'unpublish' : 'republish',
      reasons.value[item.content_id] || '',
    )
    await load()
  } catch { error.value = tab.value === 'published' ? '下架时必须填写原因。' : '恢复上架失败。' }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <header><div><span class="eyebrow">ACTIVITY MODERATION</span><h1>活动攻略审核</h1><p>审核、下架或恢复4.4活动的玩家投稿。</p></div></header>
    <nav class="tabs"><button :class="{ active: tab === 'pending' }" @click="selectTab('pending')">待审核</button><button :class="{ active: tab === 'published' }" @click="selectTab('published')">已发布</button><button :class="{ active: tab === 'unpublished' }" @click="selectTab('unpublished')">已下架</button></nav>
    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="tab === 'pending'" class="review-list">
      <p v-if="!items.length">当前没有待审核活动攻略。</p>
      <article v-for="item in items" :key="item.id"><span>{{ item.activity_title }} · {{ item.player_stage }}</span><h2>{{ item.title }}</h2><small>作者 {{ item.author_name }}</small><p>{{ item.content }}</p><textarea v-model="reasons[item.id]" rows="3" placeholder="驳回理由（驳回时必填）" /><div><button @click="decide(item.id, 'approve')">通过并发布</button><button @click="decide(item.id, 'reject')">驳回</button></div></article>
    </section>
    <section v-else class="review-list">
      <p v-if="!managed.length">当前没有对应活动攻略。</p>
      <article v-for="item in managed" :key="item.content_id"><span>{{ tab === 'published' ? '已发布' : '已下架' }}</span><h2>{{ item.title }}</h2><small>作者 {{ item.author_name }}</small><p v-if="item.reason">原因：{{ item.reason }}</p><textarea v-if="tab === 'published'" v-model="reasons[item.content_id]" rows="2" placeholder="下架原因（必填）" /><button @click="moderate(item)">{{ tab === 'published' ? '下架攻略' : '恢复上架' }}</button></article>
    </section>
  </AppShell>
</template>

<style scoped>
header p, article p, article small { color: var(--muted); }
.tabs { display: flex; gap: 8px; margin: 18px 0; }
.tabs button { border-radius: 999px; }
.tabs button.active { color: var(--gold); background: rgba(230, 201, 130, .1); }
.review-list { display: grid; gap: 16px; }
article { padding: 20px; border: 1px solid var(--line); background: var(--panel); }
article > span { color: var(--gold); font-size: 12px; }
textarea { box-sizing: border-box; width: 100%; margin-top: 12px; border: 1px solid var(--line); background: #0b1122; }
button { margin: 10px 10px 0 0; padding: 9px 14px; border: 1px solid var(--gold); background: transparent; cursor: pointer; }
</style>
