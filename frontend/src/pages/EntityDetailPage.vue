<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { getKnowledgeEntity } from '../services/api'
import type { KnowledgeEntityDetail } from '../types/catalog'

const route = useRoute()
const entity = ref<KnowledgeEntityDetail | null>(null)
const loading = ref(true)
const error = ref('')
const labels: Record<string, string> = { lightcones: '光锥智库', relics: '遗器智库', items: '物品智库', monsters: '怪物智库', characters: '角色智库' }
const kind = computed(() => String(route.params.kind))
const relatedUrl = (item: { kind: string; id: string }) => `/${item.kind}/${item.id}`

async function load() {
  loading.value = true
  error.value = ''
  try { entity.value = await getKnowledgeEntity(kind.value, String(route.params.id)) }
  catch { error.value = '这份知识档案不存在，或者数据尚未准备完成。' }
  finally { loading.value = false }
}
watch(() => [route.params.kind, route.params.id], load, { immediate: true })
</script>

<template>
  <AppShell>
    <p v-if="loading" class="catalog-state">正在调取知识档案……</p>
    <div v-else-if="error" class="catalog-state"><p class="error">{{ error }}</p><router-link :to="`/${kind}`">返回{{ labels[kind] }}</router-link></div>
    <template v-else-if="entity">
      <nav class="breadcrumbs"><router-link :to="`/${kind}`">{{ labels[kind] }}</router-link><span>/</span><b>{{ entity.name }}</b></nav>
      <section class="entity-hero">
        <div class="entity-art"><img v-if="entity.image_url" :src="entity.image_url" :alt="entity.name" /><small v-if="entity.image_status !== 'official'">分类占位图</small></div>
        <div><span class="eyebrow">{{ entity.subtitle }} · {{ entity.id }}</span><h1>{{ entity.name }}</h1><p>{{ entity.description }}</p><small v-if="entity.data_version">本地数据版本 {{ entity.data_version }}</small></div>
      </section>
      <section v-for="(section, index) in entity.sections" :key="section.name" class="detail-section entity-section">
        <div class="section-heading"><span>{{ String(index + 1).padStart(2, '0') }}</span><div><h2>{{ section.name }}</h2></div></div>
        <div class="story-content">{{ section.description }}</div>
      </section>
      <section v-if="entity.related_entities.length" class="detail-section">
        <div class="section-heading"><span>↗</span><div><h2>关联档案</h2><p>点击卡片可以跳转到对应知识分区。</p></div></div>
        <div class="related-grid"><router-link v-for="item in entity.related_entities" :key="`${item.kind}-${item.id}`" :to="relatedUrl(item)" class="related-card"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /><div><small>{{ labels[item.kind] }} · {{ item.id }}</small><h3>{{ item.name }}</h3><p>{{ item.subtitle }}</p></div><b>↗</b></router-link></div>
      </section>
      <footer v-if="entity.source_url" class="source-note">资料来源：<a :href="entity.source_url" target="_blank" rel="noreferrer">公开结构化数据</a></footer>
    </template>
  </AppShell>
</template>
