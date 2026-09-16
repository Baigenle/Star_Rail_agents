<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import AppShell from '../components/AppShell.vue'
import { getStories } from '../services/api'
import type { StoryFilters, StorySummary } from '../types/story'

const items = ref<StorySummary[]>([])
const filters = ref<StoryFilters>({
  versions: [],
  worlds: [],
  mission_types: [],
  series: [],
})
const form = reactive({
  q: '',
  version: '',
  world: '',
  mission_type: '',
  series: '',
  character: '',
})
const loading = ref(false)
const error = ref('')
const displayLimit = ref(36)
const visibleItems = computed(() => items.value.slice(0, displayLimit.value))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await getStories(form)
    items.value = result.items
    filters.value = result.filters
    displayLimit.value = 36
  } catch {
    error.value = '剧情档案暂时无法读取。'
  } finally {
    loading.value = false
  }
}

function reset() {
  Object.assign(form, {
    q: '',
    version: '',
    world: '',
    mission_type: '',
    series: '',
    character: '',
  })
  void load()
}

onMounted(load)
</script>

<template>
  <AppShell>
    <header class="story-header">
      <div>
        <span class="eyebrow">STORY ARCHIVE</span>
        <h1>剧情档案</h1>
        <p>按版本、世界与任务逐幕阅读主线和同行任务。正文来自本地知识文献。</p>
      </div>
      <strong>{{ items.length }} 个任务</strong>
    </header>

    <form class="story-filters" @submit.prevent="load">
      <input v-model.trim="form.q" placeholder="搜索任务、剧情或角色" />
      <select v-model="form.version"><option value="">全部版本</option><option v-for="item in filters.versions" :key="item">{{ item }}</option></select>
      <select v-model="form.world"><option value="">全部世界</option><option v-for="item in filters.worlds" :key="item">{{ item }}</option></select>
      <select v-model="form.mission_type"><option value="">全部任务类型</option><option v-for="item in filters.mission_types" :key="item">{{ item }}</option></select>
      <input v-model.trim="form.character" placeholder="出场角色" />
      <button type="submit">检索剧情</button>
      <button type="button" class="secondary" @click="reset">重置</button>
    </form>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading" class="catalog-state">黑塔正在整理剧情索引……</p>
    <p v-else-if="!items.length" class="catalog-state">没有符合条件的剧情任务。</p>
    <section v-else class="story-grid">
      <router-link
        v-for="item in visibleItems"
        :key="item.mission_id"
        :to="item.first_matching_chunk_id
          ? `/stories/${item.mission_id}?scene=${item.first_matching_chunk_id}`
          : `/stories/${item.mission_id}`"
      >
        <div><span>VER {{ item.version }}</span><em>{{ item.mission_type }}</em></div>
        <h2>{{ item.mission_name }}</h2>
        <small>{{ item.world }} · {{ item.series_name || '未标注系列' }}</small>
        <mark v-if="item.matched_character">
          {{ item.matched_character }}实际对白 {{ item.matched_scene_count }} 场 · 已定位首个场景
        </mark>
        <p>{{ item.summary || '当前任务未提供简介，可进入阅读场景正文。' }}</p>
        <b>阅读剧情 →</b>
      </router-link>
    </section>
    <button
      v-if="visibleItems.length < items.length"
      type="button"
      class="load-more"
      @click="displayLimit += 36"
    >
      继续显示（{{ items.length - visibleItems.length }}）
    </button>
  </AppShell>
</template>

<style scoped>
.story-header { align-items: end; }
.story-header p { color: var(--muted); }
.story-header > strong { color: var(--gold); }
.story-filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(155px, 1fr)); gap: 9px; margin: 20px 0; padding: 12px; }
.story-filters input, .story-filters select { min-width: 0; border: 1px solid var(--line); border-radius: var(--radius-md); padding: 10px; color: var(--text); background: var(--surface); }
.story-filters button { border: 1px solid var(--gold); border-radius: 8px; padding: 10px 13px; background: rgba(230, 201, 130, .13); cursor: pointer; }
.story-filters .secondary { border-color: var(--line); }
.story-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.story-grid a { display: grid; min-height: 230px; padding: 20px; border: 1px solid var(--line); border-radius: var(--radius-lg); color: inherit; background: var(--panel); text-decoration: none; }
.story-grid a:hover { border-color: rgba(230, 201, 130, .45); transform: translateY(-2px); }
.story-grid div { display: flex; justify-content: space-between; }
.story-grid span { color: var(--accent-text); font-size: 10px; }
.story-grid em, .story-grid small { color: var(--muted); font-style: normal; }
.story-grid h2 { margin: 15px 0 7px; font-size: 18px; }
.story-grid mark { width: fit-content; margin-top: 10px; padding: 5px 8px; border: 1px solid rgba(185, 148, 255, .3); border-radius: 999px; color: #cbb5ff; background: rgba(103, 69, 165, .16); font-size: 10px; }
.story-grid p { overflow: hidden; color: var(--text-secondary); font-size: 12px; line-height: 1.8; }
.story-grid b { align-self: end; color: var(--accent-text); font-size: 11px; }
.load-more { display: block; margin: 22px auto 0; border: 1px solid var(--gold); border-radius: 999px; padding: 11px 20px; background: rgba(230, 201, 130, .1); cursor: pointer; }
@media (max-width: 1100px) { .story-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 700px) { .story-grid { grid-template-columns: 1fr; } }
</style>
