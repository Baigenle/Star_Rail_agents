<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { getRelic } from '../services/api'
import type { RelicDetail } from '../types/catalog'

const route = useRoute()
const relic = ref<RelicDetail | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try { relic.value = await getRelic(String(route.params.id)) }
  catch { error.value = '这份遗器档案不存在，或者补充信息尚未完成对齐。' }
  finally { loading.value = false }
}

watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <AppShell>
    <p v-if="loading" class="catalog-state">正在融合遗器套装与部件档案……</p>
    <div v-else-if="error" class="catalog-state"><p class="error">{{ error }}</p><router-link to="/relics">返回遗器智库</router-link></div>
    <template v-else-if="relic">
      <nav class="breadcrumbs"><router-link to="/characters">游戏智库</router-link><span>/</span><router-link to="/relics">遗器</router-link><span>/</span><b>{{ relic.name }}</b></nav>
      <section class="relic-hero">
        <div class="relic-cover"><img v-if="relic.image_url" :src="relic.image_url" :alt="relic.name" /></div>
        <div><span class="eyebrow">RELIC SET · {{ relic.id }}</span><h1>{{ relic.name }}</h1><div class="trait-row"><span>{{ relic.set_type === 'cavern' ? '隧洞遗器' : '位面饰品' }}</span><span>{{ relic.piece_count }} 件套</span></div><p>{{ relic.description }}</p><small v-if="relic.acquisition">获取途径：{{ relic.acquisition }}</small></div>
      </section>
      <section class="detail-section">
        <div class="section-heading"><span>01</span><div><h2>套装效果</h2><p>{{ relic.set_type === 'cavern' ? '隧洞遗器包含二件套与四件套效果。' : '位面饰品包含二件套效果。' }}</p></div></div>
        <div class="relic-effect-grid"><article v-for="effect in relic.set_effects" :key="effect.name"><small>{{ effect.name }}</small><p>{{ effect.description }}</p></article></div>
      </section>
      <section class="detail-section">
        <div class="section-heading"><span>02</span><div><h2>套装部件</h2><p>部件名称、图片、描述与来历均已按规范套装 ID 对齐。</p></div></div>
        <div class="relic-piece-grid"><article v-for="piece in relic.pieces" :key="piece.name"><div><img v-if="piece.image_url" :src="piece.image_url" :alt="piece.name" /></div><small>{{ piece.type }}</small><h3>{{ piece.name }}</h3><p>{{ piece.description }}</p></article></div>
      </section>
      <section v-if="relic.related_entities.length" class="detail-section">
        <div class="section-heading"><span>03</span><div><h2>推荐角色</h2><p>点击角色可进入对应角色档案。</p></div></div>
        <div class="related-grid"><router-link v-for="item in relic.related_entities.filter((entry) => entry.kind === 'characters')" :key="item.id" :to="`/characters/${item.id}`" class="related-card"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /><div><small>角色智库 · {{ item.id }}</small><h3>{{ item.name }}</h3><p>{{ item.subtitle }}</p></div><b>↗</b></router-link></div>
      </section>
      <footer class="source-note"><span>资料来源：规范结构化档案<template v-if="relic.community_source_url"> · <a :href="relic.community_source_url" target="_blank" rel="noreferrer">社区补充资料</a></template></span><span>图片为本地 WebP 资源</span></footer>
    </template>
  </AppShell>
</template>
