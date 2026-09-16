<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import CharacterProgressionPlanner from '../components/CharacterProgressionPlanner.vue'
import { getCharacter } from '../services/api'
import type { CharacterDetail } from '../types/catalog'
import { itemTypeLabel } from '../utils/catalogLabels'

const route = useRoute()
const character = ref<CharacterDetail | null>(null)
const loading = ref(true)
const error = ref('')
const activeTab = ref<'overview' | 'build' | 'story' | 'skills' | 'eidolons' | 'progression' | 'items'>('overview')
const cavernRelics = computed(() => character.value?.recommended_relics.filter((item) => item.set_type === 'cavern') ?? [])
const planarRelics = computed(() => character.value?.recommended_relics.filter((item) => item.set_type === 'planar') ?? [])
const skillGroups = computed(() => {
  const skills = character.value?.skills ?? []
  return [
    {
      key: 'character',
      title: '角色技能',
      description: '普攻、战技、终结技、天赋、强化技能与秘技',
      items: skills.filter((item) => !['欢愉技', '忆灵技', '忆灵天赋'].includes(item.type ?? '')),
    },
    {
      key: 'elation',
      title: '欢愉技',
      description: '欢愉命途的特殊技能',
      items: skills.filter((item) => item.type === '欢愉技'),
    },
    {
      key: 'memosprite',
      title: '忆灵技能',
      description: '忆灵技与忆灵天赋',
      items: skills.filter((item) => ['忆灵技', '忆灵天赋'].includes(item.type ?? '')),
    },
  ].filter((group) => group.items.length)
})
const standardMaterials = computed(() => character.value?.related_items.filter((item) => item.type !== 'WeeklyMonsterDrop') ?? [])
const weeklyMaterials = computed(() => character.value?.related_items.filter((item) => item.type === 'WeeklyMonsterDrop') ?? [])

async function load() {
  loading.value = true
  error.value = ''
  try { character.value = await getCharacter(String(route.params.id)) }
  catch { error.value = '这份角色档案不存在，或者数据尚未准备完成。' }
  finally { loading.value = false }
}

onMounted(load)
watch(() => route.params.id, load)
</script>

<template>
  <AppShell>
    <p v-if="loading" class="catalog-state">正在调取角色档案……</p>
    <div v-else-if="error" class="catalog-state"><p class="error">{{ error }}</p><router-link to="/characters">返回角色智库</router-link></div>
    <template v-else-if="character">
      <nav class="breadcrumbs"><router-link to="/characters">角色智库</router-link><span>/</span><b>{{ character.name }}</b></nav>
      <section class="character-hero">
        <div class="hero-copy">
          <span class="eyebrow">CHARACTER FILE · {{ character.id }}</span>
          <div class="hero-title"><h1>{{ character.name }}</h1><span>{{ '★'.repeat(character.rarity) }}</span></div>
          <div class="trait-row">
            <span><img v-if="character.element_icon_url" :src="character.element_icon_url" alt="" />{{ character.element }}属性</span>
            <span><img v-if="character.path_icon_url" :src="character.path_icon_url" alt="" />{{ character.path }}命途</span>
            <span v-if="character.energy">终结技能量 {{ character.energy }}</span>
          </div>
          <p class="character-description">{{ character.description }}</p>
          <small>本地数据版本 {{ character.data_version || '未知' }}</small>
        </div>
        <div class="portrait-wrap"><img v-if="character.portrait_url" :src="character.portrait_url" :alt="`${character.name}角色立绘`" /></div>
      </section>
      <nav class="detail-tabs" aria-label="角色详情分类">
        <button :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">档案概览</button>
        <button :class="{ active: activeTab === 'build' }" @click="activeTab = 'build'">推荐构筑</button>
        <button :class="{ active: activeTab === 'story' }" @click="activeTab = 'story'">角色故事</button>
        <button :class="{ active: activeTab === 'skills' }" @click="activeTab = 'skills'">技能 {{ character.skills.length }}</button>
        <button :class="{ active: activeTab === 'eidolons' }" @click="activeTab = 'eidolons'">星魂 {{ character.eidolons.length }}</button>
        <button :class="{ active: activeTab === 'progression' }" @click="activeTab = 'progression'">养成规划</button>
        <button :class="{ active: activeTab === 'items' }" @click="activeTab = 'items'">关联物品 {{ character.related_items.length }}</button>
      </nav>
      <section v-if="activeTab === 'overview'" class="detail-section">
        <div class="section-heading"><span>01</span><div><h2>80 级基础属性</h2><p>由本地角色文档整理的满级基础数值。</p></div></div>
        <div class="stat-grid"><div v-for="(value, name) in character.stats" :key="name"><small>{{ name }}</small><strong>{{ value }}</strong></div></div>
        <div class="archive-note"><b>黑塔智库说明</b><p>基础数值来自结构化角色资料；构筑建议与故事来自已完成实体 ID 对齐的社区知识文档。</p></div>
      </section>
      <section v-else-if="activeTab === 'build'" class="detail-section">
        <div class="section-heading"><span>02</span><div><h2>推荐构筑</h2><p>名称已映射为游戏实体 ID，并关联本地图片。</p></div></div>
        <h3 class="recommend-heading">推荐光锥</h3>
        <div class="recommend-grid"><router-link v-for="item in character.recommended_lightcones" :key="`lc-${item.id}`" :to="`/lightcones/${item.id}`" class="recommend-card"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /><div><small>光锥 · {{ item.id }}</small><h3>{{ item.name }}</h3></div></router-link></div>
        <h3 class="recommend-heading">隧洞遗器 · 4 件套</h3>
        <div class="recommend-grid"><router-link v-for="item in cavernRelics" :key="`relic-${item.id}`" :to="`/relics/${item.id}`" class="recommend-card"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /><div><small>隧洞遗器 · {{ item.id }}</small><h3>{{ item.name }}</h3></div></router-link></div>
        <h3 class="recommend-heading">位面饰品 · 2 件套</h3>
        <div class="recommend-grid"><router-link v-for="item in planarRelics" :key="`relic-${item.id}`" :to="`/relics/${item.id}`" class="recommend-card"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /><div><small>位面饰品 · {{ item.id }}</small><h3>{{ item.name }}</h3></div></router-link></div>
        <p v-if="!character.recommended_lightcones.length && !character.recommended_relics.length" class="catalog-state">当前角色的补充攻略尚未提供可确认的推荐实体。</p>
      </section>
      <section v-else-if="activeTab === 'story'" class="detail-section">
        <div class="section-heading"><span>03</span><div><h2>角色故事</h2><p>社区资料中的角色故事已作为补充知识接入。</p></div></div>
        <div v-if="character.story" class="story-content">{{ character.story }}</div>
        <p v-else class="catalog-state">当前档案暂未收录角色故事。</p>
      </section>
      <section v-else-if="activeTab === 'skills'" class="detail-section">
        <div class="section-heading"><span>04</span><div><h2>技能档案</h2><p>按角色技能、欢愉技和忆灵技能分组整理。</p></div></div>
        <div class="skill-groups">
          <section v-for="group in skillGroups" :key="group.key" class="skill-group" :class="`skill-group--${group.key}`">
            <header><div><h3>{{ group.title }}</h3><p>{{ group.description }}</p></div><b>{{ group.items.length }}</b></header>
            <div class="entry-list"><article v-for="skill in group.items" :key="`${skill.type}-${skill.name}`" class="entry-card"><img v-if="skill.image_url" :src="skill.image_url" alt="" /><div><small>{{ skill.type || '技能' }}</small><h3>{{ skill.name }}</h3><p>{{ skill.description }}</p></div></article></div>
          </section>
        </div>
      </section>
      <section v-else-if="activeTab === 'eidolons'" class="detail-section">
        <div class="section-heading"><span>05</span><div><h2>星魂档案</h2><p>六个星魂效果的文档化展示。</p></div></div>
        <div class="eidolon-grid"><article v-for="(eidolon, index) in character.eidolons" :key="eidolon.name"><img v-if="eidolon.image_url" :src="eidolon.image_url" alt="" /><div><small>星魂 {{ index + 1 }}</small><h3>{{ eidolon.name }}</h3><p>{{ eidolon.description }}</p></div></article></div>
      </section>
      <section v-else-if="activeTab === 'progression'" class="detail-section">
        <CharacterProgressionPlanner :character-id="character.id" />
      </section>
      <section v-else class="detail-section">
        <div class="section-heading"><span>06</span><div><h2>关联物品</h2><p>每名角色统一展示 7 种常规养成材料与 2 种高阶行迹材料。</p></div></div>
        <h3 class="recommend-heading">常规养成材料 · {{ standardMaterials.length }}</h3>
        <div class="item-grid"><router-link v-for="item in standardMaterials" :key="item.id" :to="`/items/${item.id}`" class="item-card"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /><div><small>{{ itemTypeLabel(item.type) }}</small><h3>{{ item.name }}</h3><p>{{ item.description }}</p></div><b>↗</b></router-link></div>
        <h3 class="recommend-heading">历战余响 / 高阶行迹材料 · {{ weeklyMaterials.length }}</h3>
        <div class="item-grid"><router-link v-for="item in weeklyMaterials" :key="item.id" :to="`/items/${item.id}`" class="item-card item-card--weekly"><img v-if="item.image_url" :src="item.image_url" :alt="item.name" /><div><small>{{ itemTypeLabel(item.type) }}</small><h3>{{ item.name }}</h3><p>{{ item.description }}</p></div><b>↗</b></router-link></div>
      </section>
      <footer class="source-note"><span>资料来源：<a :href="character.source_url" target="_blank" rel="noreferrer">Nanoka 结构化数据</a><template v-if="character.community_source_url"> · <a :href="character.community_source_url" target="_blank" rel="noreferrer">米游社社区资料</a></template></span><span>页面使用本地文档与 WebP 资源生成</span></footer>
    </template>
  </AppShell>
</template>
