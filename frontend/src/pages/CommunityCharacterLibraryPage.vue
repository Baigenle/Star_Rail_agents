<script setup lang="ts">
import { onMounted, ref } from 'vue'

import AppShell from '../components/AppShell.vue'
import { getCommunityCharacters } from '../services/api'
import type { CustomCharacter } from '../types/customCharacter'

const items = ref<CustomCharacter[]>([])
const loading = ref(true)
onMounted(async () => {
  try { items.value = await getCommunityCharacters() } finally { loading.value = false }
})
</script>

<template>
  <AppShell>
    <header><div><span class="eyebrow">COMMUNITY ARCHIVE</span><h1>社区角色库</h1><p>这里全部是经过审核的玩家创作，不属于官方角色事实，也不会写入官方 RAG。</p></div></header>
    <p v-if="loading" class="catalog-state">正在读取社区角色…</p>
    <section v-else-if="items.length" class="community-grid">
      <router-link v-for="item in items" :key="item.id" :to="`/community/characters/${item.id}`">
        <span>{{ item.payload.name?.slice(0, 1) }}</span><small>玩家创作 · v{{ item.version_number }}</small>
        <h2>{{ item.name }}</h2><p>{{ item.payload.element }} · {{ item.payload.path }}</p><em>作者 {{ item.author_name }}</em>
      </router-link>
    </section>
    <div v-else class="catalog-state">还没有通过审核的社区角色。</div>
  </AppShell>
</template>

<style scoped>
header p, .community-grid p, .community-grid em { color: var(--muted); }
.community-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: .8rem; }
.community-grid a { padding: 1.2rem; border: 1px solid var(--line); color: inherit; text-decoration: none; background: var(--panel); }
.community-grid a > span { display: grid; place-items: center; width: 5rem; height: 5rem; margin-bottom: 1rem; border: 1px solid var(--blue); border-radius: 50%; color: var(--blue); font-size: 2rem; }
.community-grid small { color: var(--gold); }
.community-grid h2 { margin-bottom: .25rem; }
.community-grid em { font-size: .8rem; font-style: normal; }
</style>
