<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from '../components/AppShell.vue'
import { getActivity, getActivityGuides, submitActivityGuide } from '../services/api'
import { useAuthStore } from '../stores/auth'
import type { ActivityDetail, ActivityGuide } from '../types/activity'

const route = useRoute()
const auth = useAuthStore()
const item = ref<ActivityDetail | null>(null)
const guides = ref<ActivityGuide[]>([])
const error = ref('')
const success = ref('')
const form = ref({ title: '', content: '', player_stage: 'all' })
const assetUrl = (path?: string) => path ? `http://localhost:8000${path}` : ''

async function load() {
  try {
    item.value = await getActivity(String(route.params.id))
    guides.value = await getActivityGuides(String(route.params.id))
  } catch { error.value = '活动档案不存在或暂时不可用。' }
}
async function submit() {
  error.value = ''
  success.value = ''
  try {
    await submitActivityGuide(String(route.params.id), form.value)
    success.value = '攻略已提交，管理员审核通过后会在社区攻略区公开。'
    form.value = { title: '', content: '', player_stage: 'all' }
  } catch { error.value = '投稿失败，请确认已登录且正文不少于 40 字。' }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <p v-if="error && !item" class="error">{{ error }}</p>
    <template v-else-if="item">
      <header><div><span class="eyebrow">VERSION {{ item.version }}</span><h1>{{ item.title }}</h1><p>{{ item.schedule }}</p></div><router-link class="agent-badge" to="/">询问活动攻略 Agent</router-link></header>
      <img v-if="item.image?.api_path" class="activity-hero" :src="assetUrl(item.image.api_path)" :alt="item.title" />
      <section v-if="item.detail_available" class="detail-section">
        <article v-for="section in item.detail?.sections" :key="section.title">
          <h2>{{ section.title }}</h2>
          <p v-for="paragraph in section.paragraphs" :key="paragraph">{{ paragraph }}</p>
        </article>
      </section>
      <section v-else class="detail-section"><h2>往期活动索引</h2><p>当前仅保留名称、版本、时间与图片，不提供详情和攻略，避免用不完整资料生成结论。</p></section>

      <template v-if="item.community_submission_available">
        <section class="detail-section"><h2>社区攻略</h2><p v-if="!guides.length">暂无已审核攻略。</p><article v-for="guide in guides" :key="guide.id" class="guide"><b>{{ guide.title }}</b><small>{{ guide.author_name }} · {{ guide.player_stage }}</small><p>{{ guide.content }}</p></article></section>
        <section class="detail-section"><h2>投稿活动攻略</h2><p v-if="!auth.user">登录后可以投稿，内容会进入管理员审核。</p><form v-else @submit.prevent="submit"><input v-model="form.title" required minlength="2" placeholder="攻略标题" /><select v-model="form.player_stage"><option value="all">全部阶段</option><option value="beginner">新手</option><option value="midgame">中期</option><option value="endgame">后期</option></select><textarea v-model="form.content" required minlength="40" rows="8" placeholder="写清机制、队伍思路、操作顺序和注意事项……" /><button type="submit">提交审核</button></form><p v-if="success" class="success">{{ success }}</p><p v-if="error" class="error">{{ error }}</p></section>
      </template>
    </template>
  </AppShell>
</template>

<style scoped>
header p, .detail-section p { color: var(--muted); line-height: 1.8; }
.activity-hero { width: 100%; max-height: 420px; object-fit: cover; border: 1px solid var(--line); border-radius: 16px; }
.agent-badge { text-decoration: none; }
.guide { margin-top: 14px; padding: 16px; border-left: 2px solid var(--gold); background: rgba(255,255,255,.025); }
.guide b, .guide small { display: block; }
.guide small { margin-top: 5px; color: var(--muted); }
form { display: grid; align-items: stretch; }
input, select { border: 1px solid var(--line); padding: 11px; color: inherit; background: #0b1122; }
textarea { min-height: 160px; border: 1px solid var(--line); }
.success { color: #75cfa6 !important; }
</style>
