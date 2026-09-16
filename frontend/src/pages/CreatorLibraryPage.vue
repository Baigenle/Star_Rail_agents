<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { createCustomCharacter, getMyCustomCharacters } from '../services/api'
import type { CustomCharacter } from '../types/customCharacter'

const router = useRouter()
const items = ref<CustomCharacter[]>([])
const loading = ref(true)
const creating = ref(false)

async function load() {
  loading.value = true
  try { items.value = await getMyCustomCharacters() } finally { loading.value = false }
}
async function create() {
  creating.value = true
  try {
    const character = await createCustomCharacter()
    await router.push(`/creator/${character.id}`)
  } finally { creating.value = false }
}
onMounted(load)
</script>

<template>
  <AppShell>
    <header class="creator-title"><div><span class="eyebrow">HERTA CREATION LAB</span><h1>角色创作工坊</h1><p>玩家作品与官方智库完全隔离。黑塔会逐阶段记录你明确确认的数据。</p></div><button :disabled="creating" @click="create">{{ creating ? '创建中…' : '新建角色' }}</button></header>
    <aside class="review-guide">
      <div><strong>发布流程</strong><p>完成四阶段 → 提交社区审核 → 等待审核结果 → 通过后进入社区角色库。</p></div>
      <small>你可以继续修改私人草稿；提交后的审核状态和驳回原因会显示在作品档案中。</small>
    </aside>
    <p v-if="loading" class="catalog-state">正在读取你的草稿…</p>
    <section v-else-if="items.length" class="creation-list">
      <router-link v-for="item in items" :key="item.id" :to="`/creator/${item.id}`">
        <span>{{ item.payload.name?.slice(0, 1) || '？' }}</span>
        <div><small>{{ item.status }} · v{{ item.version_number }}</small><h2>{{ item.name }}</h2><p>{{ item.payload.element || '属性待定' }} · {{ item.payload.path || '命途待定' }}</p></div>
      </router-link>
    </section>
    <div v-else class="empty-creator"><h2>还没有自定义角色</h2><p>建立第一份草稿，本天才会告诉你缺了哪些数据。</p><button @click="create">开始创作</button></div>
  </AppShell>
</template>

<style scoped>
.creator-title { display: flex; justify-content: space-between; gap: 1rem; }
.creator-title p, .creation-list p, .empty-creator p { color: var(--muted); }
button { border: 1px solid var(--gold); padding: .75rem 1rem; background: rgba(230,201,130,.12); cursor: pointer; }
.creation-list { display: grid; gap: .75rem; }
.creation-list a { display: flex; gap: 1rem; padding: 1rem; border: 1px solid var(--line); color: inherit; text-decoration: none; background: var(--panel); }
.creation-list a > span { display: grid; place-items: center; width: 4rem; height: 4rem; border: 1px solid var(--blue); border-radius: 50%; color: var(--blue); font-size: 1.5rem; }
.creation-list h2, .creation-list p { margin: .2rem 0; }
.empty-creator { padding: 4rem; border: 1px solid var(--line); text-align: center; background: var(--panel); }
.review-guide { display: grid; gap: .5rem; align-items: center; margin-bottom: 1rem; padding: 1rem; border: 1px solid rgba(230, 201, 130, .28); background: rgba(114, 84, 28, .1); }
.review-guide p { margin: .25rem 0; color: var(--muted); }
.review-guide small { color: var(--muted); }
</style>
