<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import CustomCharacterPreview from '../components/CustomCharacterPreview.vue'
import { getCommunityCharacter } from '../services/api'
import type { CustomCharacter } from '../types/customCharacter'

const route = useRoute()
const character = ref<CustomCharacter | null>(null)
const error = ref('')
onMounted(async () => {
  try { character.value = await getCommunityCharacter(String(route.params.id)) }
  catch { error.value = '社区角色不存在或尚未公开。' }
})
</script>

<template>
  <AppShell>
    <div v-if="error" class="catalog-state">{{ error }}</div>
    <template v-else-if="character">
      <nav class="breadcrumbs"><router-link to="/community/characters">社区角色库</router-link><span>/</span><b>{{ character.name }}</b></nav>
      <div class="community-detail">
        <CustomCharacterPreview :payload="character.payload" :status="`玩家创作 · v${character.version_number}`" />
        <article>
          <span class="eyebrow">PLAYER CREATION</span><h1>{{ character.name }}</h1>
          <p>作者：{{ character.author_name }} · 审核公开版本 v{{ character.version_number }}</p>
          <h2>创作说明</h2><p>{{ character.payload.summary }}</p>
          <h2>战斗设计</h2><p>{{ character.payload.core_mechanics }}</p>
          <h2 v-if="character.payload.story">角色故事</h2><p v-if="character.payload.story" class="story">{{ character.payload.story }}</p>
          <div class="source-warning">数据来源：玩家确认的自定义角色版本。此页面不代表官方游戏内容。</div>
        </article>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.community-detail { display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 2rem; align-items: start; }
article > p { color: #aab4ca; line-height: 1.8; }
.story { white-space: pre-wrap; }
.source-warning { margin-top: 2rem; padding: 1rem; border-left: 2px solid var(--gold); background: rgba(230,201,130,.08); }
@media (max-width: 800px) { .community-detail { grid-template-columns: 1fr; } }
</style>
