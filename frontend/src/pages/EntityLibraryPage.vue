<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import KnowledgeTabs from '../components/KnowledgeTabs.vue'
import { getKnowledgeEntities } from '../services/api'
import type { KnowledgeEntitySummary } from '../types/catalog'

const route = useRoute()
const entities = ref<KnowledgeEntitySummary[]>([])
const loading = ref(true)
const error = ref('')
const search = ref('')
const rarity = ref('全部')
const path = ref('全部')
const relicType = ref('全部')
const visibleLimit = ref(160)
const paths = ['全部', '毁灭', '巡猎', '智识', '同谐', '虚无', '存护', '丰饶', '记忆', '欢愉']
const config: Record<string, { title: string; eyebrow: string; description: string }> = {
  lightcones: { title: '光锥智库', eyebrow: 'LIGHT CONE ARCHIVE', description: '查询光锥属性、叠影效果、晋阶材料与适配角色。' },
  relics: { title: '遗器智库', eyebrow: 'RELIC ARCHIVE', description: '查询遗器套装效果、部件以及推荐使用角色。' },
  items: { title: '物品智库', eyebrow: 'ITEM ARCHIVE', description: '查询材料介绍、背景说明、获取来源与关联角色。' },
  monsters: { title: '怪物智库', eyebrow: 'ENEMY ARCHIVE', description: '查询敌对生物介绍、掉落材料以及相关物品。' },
}
const kind = computed(() => String(route.params.kind))
const page = computed(() => config[kind.value] ?? config.items)
const filtered = computed(() => {
  const query = search.value.trim().toLowerCase()
  return entities.value
    .filter((item) => (!query || item.name.toLowerCase().includes(query) || item.id.includes(query))
      && (rarity.value === '全部' || item.rarity === Number(rarity.value))
      && (path.value === '全部' || item.path === path.value)
      && (relicType.value === '全部' || item.set_type === relicType.value))
    .sort((a, b) => (b.rarity ?? 0) - (a.rarity ?? 0) || Number(b.id) - Number(a.id) || a.name.localeCompare(b.name, 'zh-CN'))
})
const visible = computed(() => filtered.value.slice(0, visibleLimit.value))

async function load() {
  loading.value = true
  error.value = ''
  search.value = ''
  rarity.value = '全部'
  path.value = '全部'
  relicType.value = '全部'
  visibleLimit.value = 160
  try { entities.value = await getKnowledgeEntities(kind.value) }
  catch { error.value = '这个知识分区暂时无法读取。' }
  finally { loading.value = false }
}

watch(() => route.params.kind, load, { immediate: true })
</script>

<template>
  <AppShell>
    <KnowledgeTabs />
    <header class="catalog-header">
      <div><span class="eyebrow">{{ page.eyebrow }}</span><h1>{{ page.title }}</h1><p>{{ page.description }}</p></div>
      <span class="archive-count">{{ filtered.length }} / {{ entities.length }} 份档案</span>
    </header>
    <section class="catalog-toolbar">
      <label class="catalog-search"><span>⌕</span><input v-model="search" :aria-label="`搜索${page.title}`" placeholder="输入名称或实体 ID" /></label>
      <select v-if="kind === 'lightcones'" v-model="rarity" aria-label="筛选光锥稀有度"><option>全部</option><option value="5">5 星</option><option value="4">4 星</option><option value="3">3 星</option></select>
      <select v-if="kind === 'lightcones'" v-model="path" aria-label="筛选光锥命途"><option v-for="item in paths" :key="item">{{ item }}</option></select>
      <select v-if="kind === 'relics'" v-model="relicType" aria-label="筛选遗器类型"><option value="全部">全部</option><option value="cavern">隧洞遗器 · 4 件</option><option value="planar">位面饰品 · 2 件</option></select>
    </section>
    <p v-if="loading" class="catalog-state">黑塔正在整理档案……</p>
    <p v-else-if="error" class="catalog-state error">{{ error }}</p>
    <section v-else class="knowledge-grid">
      <router-link v-for="item in visible" :key="item.id" :to="`/${kind}/${item.id}`" class="knowledge-card">
        <div class="knowledge-image"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" loading="lazy" /></div>
        <div><small><template v-if="item.set_type">{{ item.set_type === 'cavern' ? '隧洞遗器' : '位面饰品' }} · {{ item.piece_count }} 件</template><template v-else>{{ item.rarity ? '★'.repeat(item.rarity) : item.subtitle }}<template v-if="item.path"> · {{ item.path }}</template></template> · {{ item.id }}</small><h2>{{ item.name }}</h2><em v-if="item.image_status !== 'official'">分类占位图</em></div>
        <b>↗</b>
      </router-link>
    </section>
    <button v-if="visible.length < filtered.length" class="load-more" @click="visibleLimit += 160">继续加载（剩余 {{ filtered.length - visible.length }}）</button>
    <p v-if="!loading && !error && !filtered.length" class="catalog-state">没有符合条件的档案。</p>
  </AppShell>
</template>
