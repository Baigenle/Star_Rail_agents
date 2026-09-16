<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { getLightcone } from '../services/api'
import type { LightconeDetail } from '../types/catalog'

const route = useRoute()
const lightcone = ref<LightconeDetail | null>(null)
const loading = ref(true)
const error = ref('')
const levelIndex = ref(6)
const superimposition = ref(1)
const milestones = [1, 20, 30, 40, 50, 60, 70, 80]
const numberFormat = new Intl.NumberFormat('zh-CN')
const level = computed(() => milestones[levelIndex.value])

const currentStats = computed(() => lightcone.value?.level_stats.find((item) => item.level === level.value))
const currentEffect = computed(() => lightcone.value?.superimposition_effects[superimposition.value - 1] || '当前档案暂未记录叠影效果。')
const currentMaterialLevel = computed(() => {
  if (!lightcone.value) return 0
  return Object.keys(lightcone.value.promotion_materials)
    .map(Number)
    .filter((value) => value <= level.value)
    .sort((a, b) => b - a)[0]
})
const currentMaterials = computed(() => {
  if (!lightcone.value || !currentMaterialLevel.value) return []
  return lightcone.value.promotion_materials[String(currentMaterialLevel.value)] ?? []
})
const relatedCharacters = computed(() => lightcone.value?.related_entities.filter((item) => item.kind === 'characters') ?? [])

async function load() {
  loading.value = true
  error.value = ''
  levelIndex.value = 6
  superimposition.value = 1
  try { lightcone.value = await getLightcone(String(route.params.id)) }
  catch { error.value = '这份光锥档案不存在，或者融合数据尚未准备完成。' }
  finally { loading.value = false }
}

watch(() => route.params.id, load, { immediate: true })
</script>

<template>
  <AppShell>
    <p v-if="loading" class="catalog-state">正在融合光锥属性与养成档案……</p>
    <div v-else-if="error" class="catalog-state"><p class="error">{{ error }}</p><router-link to="/lightcones">返回光锥智库</router-link></div>
    <template v-else-if="lightcone">
      <nav class="breadcrumbs"><router-link to="/characters">游戏智库</router-link><span>/</span><router-link to="/lightcones">光锥</router-link><span>/</span><b>{{ lightcone.name }}</b></nav>

      <section class="lightcone-hero">
        <div class="lightcone-art"><img v-if="lightcone.image_url" :src="lightcone.image_url" :alt="lightcone.name" /></div>
        <div class="lightcone-copy">
          <span class="eyebrow">LIGHT CONE · {{ lightcone.id }}</span>
          <h1>{{ lightcone.name }}</h1>
          <div class="trait-row"><span class="rarity-stars">{{ '★'.repeat(lightcone.rarity ?? 0) }}</span><span>{{ lightcone.path || '命途待确认' }}</span></div>
          <p>{{ lightcone.lore_description || lightcone.description || '当前档案暂未提供光锥描述。' }}</p>
        </div>
      </section>

      <section class="detail-section lightcone-control">
        <div class="section-heading"><span>01</span><div><h2>等级</h2><p>拖动等级查看对应基础属性与累计晋阶材料。</p></div><strong>{{ level }}</strong></div>
        <input v-model.number="levelIndex" class="archive-range" type="range" min="0" :max="milestones.length - 1" step="1" aria-label="光锥等级" />
        <div class="range-labels"><span v-for="item in milestones" :key="item">{{ item }}</span></div>
        <div v-if="currentStats" class="lightcone-stat-list">
          <div><span>基础生命值</span><strong>{{ currentStats.hp }}</strong></div>
          <div><span>基础攻击力</span><strong>{{ currentStats.attack }}</strong></div>
          <div><span>基础防御力</span><strong>{{ currentStats.defence }}</strong></div>
        </div>
      </section>

      <section class="detail-section lightcone-control">
        <div class="section-heading"><span>02</span><div><h2>叠影</h2><p>查看叠影 1 至 5 的完整效果变化。</p></div><strong>效果 {{ superimposition }}</strong></div>
        <input v-model.number="superimposition" class="archive-range" type="range" min="1" max="5" step="1" aria-label="光锥叠影等级" />
        <div class="range-labels compact"><span v-for="item in 5" :key="item">{{ item }}</span></div>
        <article class="effect-document"><h3>{{ lightcone.effect_name || '光锥效果' }}</h3><p>{{ currentEffect }}</p></article>
      </section>

      <section class="detail-section">
        <div class="section-heading"><span>03</span><div><h2>晋阶材料</h2><p>等级 {{ currentMaterialLevel }} 晋阶节点对应的累计材料；点击物品可进入物品档案。</p></div></div>
        <div v-if="currentMaterials.length" class="promotion-grid">
          <router-link v-for="material in currentMaterials" :key="material.id" :to="`/items/${material.id}`" class="promotion-card">
            <div><img v-if="material.image_url" :src="material.image_url" :alt="material.name" /></div>
            <small>{{ material.name }}</small><strong>×{{ numberFormat.format(material.quantity) }}</strong>
          </router-link>
        </div>
        <p v-else class="empty-note">等级 1 无需晋阶材料。</p>
      </section>

      <section v-if="relatedCharacters.length" class="detail-section">
        <div class="section-heading"><span>04</span><div><h2>关联角色</h2><p>来自已对齐攻略档案的光锥推荐关系。</p></div></div>
        <div class="related-grid"><router-link v-for="item in relatedCharacters" :key="item.id" :to="`/characters/${item.id}`" class="related-card"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /><div><small>角色智库 · {{ item.id }}</small><h3>{{ item.name }}</h3><p>{{ item.subtitle }}</p></div><b>↗</b></router-link></div>
      </section>
    </template>
  </AppShell>
</template>
