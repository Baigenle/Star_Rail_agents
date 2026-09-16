<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { getItem } from '../services/api'
import type { ItemDetail } from '../types/catalog'
import { itemTypeLabel, rarityLabel } from '../utils/catalogLabels'

const route = useRoute()
const item = ref<ItemDetail | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  try { item.value = await getItem(String(route.params.id)) }
  catch { error.value = '没有找到这件物品的本地档案。' }
  finally { loading.value = false }
}
onMounted(load)
watch(() => route.params.id, load)
</script>

<template>
  <AppShell>
    <p v-if="loading" class="catalog-state">正在调取物品档案……</p>
    <div v-else-if="error" class="catalog-state"><p class="error">{{ error }}</p><router-link to="/items">返回物品智库</router-link></div>
    <template v-else-if="item">
      <nav class="breadcrumbs"><router-link to="/items">物品智库</router-link><span>/</span><strong>{{ item.name }}</strong></nav>
      <section class="item-hero">
        <div class="item-figure"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /></div>
        <div><span class="eyebrow">ITEM FILE · {{ item.id }}</span><h1>{{ item.name }}</h1><div class="item-tags"><span>{{ itemTypeLabel(item.type) }}</span><span>{{ rarityLabel(item.rarity) }}</span><span v-if="item.pile_limit">堆叠上限 {{ item.pile_limit }}</span></div><p class="item-lead">{{ item.description || '暂无简短说明。' }}</p></div>
      </section>
      <section class="detail-section item-document"><div class="section-heading"><span>01</span><div><h2>物品说明</h2><p>来自本地结构化物品文档。</p></div></div><p>{{ item.background || item.description || '当前文档没有提供更多背景说明。' }}</p></section>
      <section class="detail-section"><div class="section-heading"><span>02</span><div><h2>获取来源</h2><p>游戏内可确认的获取途径。</p></div></div><ul class="source-list"><li v-for="source in item.sources" :key="source">{{ source }}</li><li v-if="!item.sources.length">当前数据未记录明确来源。</li></ul></section>
      <section v-if="item.related_entities.length" class="detail-section"><div class="section-heading"><span>03</span><div><h2>关联角色</h2><p>点击角色可跳转到角色智库详情。</p></div></div><div class="related-grid"><router-link v-for="related in item.related_entities" :key="related.id" :to="`/characters/${related.id}`" class="related-card"><img v-if="related.image_url" :src="related.image_url" :alt="related.name" /><div><small>角色智库 · {{ related.id }}</small><h3>{{ related.name }}</h3><p>{{ related.subtitle }}</p></div><b>↗</b></router-link></div></section>
      <footer class="source-note"><router-link to="/items">← 返回物品智库</router-link><a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noreferrer">查看原始数据页面 ↗</a></footer>
    </template>
  </AppShell>
</template>
