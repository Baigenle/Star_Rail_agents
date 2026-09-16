<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppShell from '../components/AppShell.vue'
import { getActivities } from '../services/api'
import type { ActivitySummary } from '../types/activity'

const items = ref<ActivitySummary[]>([])
const selectedVersion = ref('4.4')
const loading = ref(true)
const error = ref('')
const versions = computed(() => [...new Set(items.value.map((item) => item.version))].reverse())
const visible = computed(() => items.value.filter((item) => !selectedVersion.value || item.version === selectedVersion.value))
const assetUrl = (path?: string) => path ? `http://localhost:8000${path}` : ''

onMounted(async () => {
  try { items.value = await getActivities() }
  catch { error.value = '活动资料读取失败。' }
  finally { loading.value = false }
})
</script>

<template>
  <AppShell>
    <header>
      <div><span class="eyebrow">ACTIVITY ARCHIVE</span><h1>活动智库</h1><p>4.4 活动提供详情、攻略与投稿；往期活动保留可检索索引。</p></div>
      <span class="agent-badge">193 条活动档案</span>
    </header>
    <div class="activity-toolbar">
      <label>版本
        <select v-model="selectedVersion">
          <option value="">全部</option>
          <option v-for="version in versions" :key="version" :value="version">{{ version }}</option>
        </select>
      </label>
      <small>{{ visible.length }} 项</small>
    </div>
    <p v-if="loading" class="catalog-state">正在读取活动档案……</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <section v-else class="activity-grid">
      <router-link v-for="item in visible" :key="item.id" :to="`/activities/${item.id}`" class="activity-card">
        <img v-if="item.image?.api_path" :src="assetUrl(item.image.api_path)" :alt="item.title" />
        <div><span>VERSION {{ item.version }}</span><h2>{{ item.title }}</h2><p>{{ item.schedule || '时间资料未提供' }}</p><small>{{ item.detail_available ? '4.4 详情与攻略可用' : '往期索引' }}</small></div>
      </router-link>
    </section>
  </AppShell>
</template>

<style scoped>
header p { color: var(--muted); }
.activity-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 14px 16px; border: 1px solid var(--line); background: var(--panel); }
select { margin-left: 10px; padding: 7px 28px 7px 10px; border: 1px solid var(--line); color: inherit; background: #0b1122; }
.activity-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 16px; }
.activity-card { min-height: 310px; overflow: hidden; border: 1px solid var(--line); border-radius: 14px; color: inherit; background: var(--panel); text-decoration: none; transition: .2s; }
.activity-card:hover { transform: translateY(-3px); border-color: rgba(230,201,130,.45); }
.activity-card img { width: 100%; height: 160px; object-fit: cover; background: #0b1122; }
.activity-card div { padding: 18px; }
.activity-card span, .activity-card small { color: var(--gold); font-size: 11px; }
.activity-card h2 { margin: 8px 0; font-size: 20px; }
.activity-card p { min-height: 42px; color: var(--muted); font-size: 12px; }
</style>
