<script setup lang="ts">
import { computed } from 'vue'

import type { CustomCharacterPayload } from '../types/customCharacter'

const props = defineProps<{ payload: CustomCharacterPayload; status?: string }>()
const colors: Record<string, string> = {
  物理: '#b9b4a7', 火: '#ef6b58', 冰: '#79bde8', 雷: '#a98ae9',
  风: '#6bc6a4', 量子: '#7b74e8', 虚数: '#e3bf58',
}
const initial = computed(() => props.payload.name?.slice(0, 1) || '？')
const color = computed(() => colors[props.payload.element ?? ''] ?? '#8ba7ff')
</script>

<template>
  <aside class="custom-preview" :style="{ '--character-color': color }">
    <div class="preview-mark" aria-label="模板角色头像">{{ initial }}</div>
    <span class="preview-label">PLAYER CREATION · {{ status || 'DRAFT' }}</span>
    <h2>{{ payload.name || '未命名角色' }}</h2>
    <p class="preview-meta">{{ payload.rarity ? `${payload.rarity} 星` : '稀有度待定' }} · {{ payload.element || '属性待定' }} · {{ payload.path || '命途待定' }}</p>
    <p>{{ payload.summary || '角色简介会显示在这里。' }}</p>
    <dl>
      <template v-if="payload.roles?.length"><dt>定位</dt><dd>{{ payload.roles.join(' / ') }}</dd></template>
      <template v-if="payload.core_mechanics"><dt>核心机制</dt><dd>{{ payload.core_mechanics }}</dd></template>
      <template v-if="payload.mechanic_tags?.length"><dt>战斗标签</dt><dd>{{ payload.mechanic_tags.join(' · ') }}</dd></template>
    </dl>
    <div v-if="payload.base_stats" class="preview-stats">
      <span>生命 {{ payload.base_stats.hp }}</span><span>攻击 {{ payload.base_stats.attack }}</span>
      <span>防御 {{ payload.base_stats.defence }}</span><span>速度 {{ payload.base_stats.speed }}</span>
      <span>嘲讽 {{ payload.base_stats.taunt }}</span><span>能量 {{ payload.base_stats.energy }}</span>
    </div>
    <section v-if="Object.keys(payload.skills ?? {}).length">
      <h3>技能档案</h3>
      <p v-for="(description, key) in payload.skills" :key="key"><b>{{ key }}</b>{{ description }}</p>
    </section>
  </aside>
</template>

<style scoped>
.custom-preview { position: sticky; top: 2rem; align-self: start; padding: 1.5rem; border: 1px solid color-mix(in srgb, var(--character-color) 45%, transparent); color: #f2eee5; background: #202638; }
.preview-mark { display: grid; place-items: center; width: 8rem; height: 8rem; margin-bottom: 1.25rem; border: 1px solid var(--character-color); border-radius: 50%; color: var(--character-color); font-size: 3rem; background: radial-gradient(circle, color-mix(in srgb, var(--character-color) 22%, transparent), transparent 70%); }
.preview-label { color: var(--character-color); font-size: .7rem; letter-spacing: .12em; }
h2, h3 { color: #f2eee5; }
h2 { margin-bottom: .25rem; font-size: 2rem; }
.preview-meta { color: #e9c875 !important; }
p, dd { color: #cbd0dc !important; line-height: 1.7; }
dl { display: grid; gap: .45rem; }
dt { color: #aeb5c4; font-size: .72rem; }
dd { margin: 0 0 .6rem; }
.preview-stats { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; padding-top: 1rem; border-top: 1px solid rgba(216, 209, 205, .22); color: #e4e1dc; }
section { margin-top: 1.5rem; }
section p { display: grid; gap: .2rem; }
section b { color: #f2eee5; }
</style>
