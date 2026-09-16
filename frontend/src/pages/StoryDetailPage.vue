<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { getStory, getStoryScene } from '../services/api'
import type { StoryDetail, StoryScene } from '../types/story'

const route = useRoute()
const router = useRouter()
const story = ref<StoryDetail | null>(null)
const scene = ref<StoryScene | null>(null)
const error = ref('')
const activeChunkId = computed(() => String(route.query.scene || ''))

async function openScene(chunkId: string, updateUrl = true) {
  if (!story.value || !chunkId) return
  scene.value = await getStoryScene(story.value.mission_id, chunkId)
  if (updateUrl && activeChunkId.value !== chunkId) {
    await router.replace({ query: { ...route.query, scene: chunkId } })
  }
  window.setTimeout(() => {
    document.querySelector('.active-scene')?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  })
}

async function load() {
  error.value = ''
  try {
    story.value = await getStory(String(route.params.id))
    const requested = activeChunkId.value
    const first = story.value.scenes[0]?.chunk_id
    if (requested || first) await openScene(requested || first, !requested)
  } catch {
    error.value = '没有找到这段剧情，或者剧情索引尚未准备好。'
  }
}

watch(() => route.params.id, load)
watch(activeChunkId, (chunkId) => {
  if (chunkId && chunkId !== scene.value?.chunk_id) void openScene(chunkId, false)
})
onMounted(load)
</script>

<template>
  <AppShell>
    <nav class="breadcrumbs">
      <router-link to="/stories">剧情档案</router-link><span>/</span>
      <strong>{{ story?.mission_name || '读取中' }}</strong>
    </nav>
    <p v-if="error" class="error">{{ error }}</p>
    <template v-else-if="story">
      <header class="story-hero">
        <div>
          <span class="eyebrow">{{ story.mission_type }} · VER {{ story.version }}</span>
          <h1>{{ story.mission_name }}</h1>
          <p>{{ story.world }} · {{ story.series_name || '未标注系列' }}</p>
        </div>
        <a :href="story.source_url" target="_blank" rel="noreferrer">查看文献来源 ↗</a>
      </header>

      <div class="story-reader">
        <aside aria-label="剧情场景目录">
          <button
            v-for="item in story.scenes"
            :key="item.chunk_id"
            type="button"
            :class="{ active: item.chunk_id === scene?.chunk_id }"
            @click="openScene(item.chunk_id)"
          >
            <small>SCENE {{ item.chunk_order }}</small>
            <strong>{{ item.scene_title }}</strong>
            <span>{{ item.location || '地点未标注' }}</span>
          </button>
        </aside>

        <article v-if="scene" class="active-scene">
          <div class="scene-meta">
            <span>场景 {{ scene.chunk_order }}</span>
            <small>{{ scene.location || '地点未标注' }}</small>
          </div>
          <h2>{{ scene.scene_title }}</h2>
          <p class="scene-content">{{ scene.content }}</p>
          <footer>
            <button
              type="button"
              :disabled="!scene.previous_chunk_id"
              @click="scene.previous_chunk_id && openScene(scene.previous_chunk_id)"
            >← 上一场景</button>
            <button
              type="button"
              :disabled="!scene.next_chunk_id"
              @click="scene.next_chunk_id && openScene(scene.next_chunk_id)"
            >下一场景 →</button>
          </footer>
        </article>
      </div>
    </template>
  </AppShell>
</template>

<style scoped>
.story-hero { padding: 25px; border: 1px solid var(--line); border-radius: 16px; background: var(--panel); }
.story-hero h1 { margin: 8px 0; }
.story-hero p { color: var(--muted); }
.story-hero a { color: var(--gold); text-decoration: none; }
.story-reader { display: grid; grid-template-columns: 280px minmax(0, 1fr); gap: 18px; margin-top: 18px; }
.story-reader aside { position: sticky; top: 18px; overflow-y: auto; max-height: calc(100vh - 36px); padding: 10px; border: 1px solid var(--line); border-radius: 14px; background: rgba(8, 13, 27, .82); }
.story-reader aside button { display: grid; width: 100%; gap: 5px; margin-bottom: 6px; border: 1px solid transparent; border-radius: 10px; padding: 12px; color: inherit; text-align: left; background: transparent; cursor: pointer; }
.story-reader aside button.active { border-color: rgba(185, 148, 255, .48); background: rgba(128, 82, 216, .16); }
.story-reader aside small { color: var(--gold); font-size: 9px; }
.story-reader aside span { color: var(--muted); font-size: 10px; }
.story-reader article { scroll-margin-top: 18px; padding: 30px; border: 1px solid rgba(185, 148, 255, .3); border-radius: 16px; background: linear-gradient(145deg, rgba(18, 25, 48, .92), rgba(7, 12, 25, .94)); }
.scene-meta { display: flex; justify-content: space-between; color: var(--gold); }
.scene-content { color: #b9c2d6; white-space: pre-wrap; line-height: 2; overflow-wrap: anywhere; }
footer { display: flex; justify-content: space-between; margin-top: 28px; padding-top: 18px; border-top: 1px solid var(--line); }
footer button { border: 1px solid var(--line); border-radius: 9px; padding: 10px 13px; background: rgba(157, 181, 255, .08); cursor: pointer; }
footer button:disabled { opacity: .35; cursor: default; }
@media (max-width: 800px) { .story-reader { grid-template-columns: 1fr; } .story-reader aside { position: static; max-height: 320px; } }
</style>
