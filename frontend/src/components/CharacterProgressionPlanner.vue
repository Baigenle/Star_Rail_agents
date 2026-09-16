<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import {
  calculateProgression,
  getProgressionProfile,
  getSavedProgression,
  saveProgression,
} from '../services/api'
import { useAuthStore } from '../stores/auth'
import type { ProgressionCalculation, ProgressionProfile, SkillRange } from '../types/progression'

const props = defineProps<{ characterId: string }>()
const auth = useAuthStore()
const profile = ref<ProgressionProfile | null>(null)
const result = ref<ProgressionCalculation | null>(null)
const loading = ref(true)
const calculating = ref(false)
const saving = ref(false)
const message = ref('')
const currentLevel = ref(1)
const targetLevel = ref(70)
const eidolon = ref(0)
const ranges = reactive<Record<string, SkillRange>>({})

const sortedMaterials = computed(() => result.value?.materials ?? [])

function initializeTracks(saved?: {
  current_skills: Record<string, number>
  target_skills: Record<string, number>
}) {
  if (!profile.value) return
  for (const [key, track] of Object.entries(profile.value.tracks)) {
    ranges[key] = {
      from_level: saved?.current_skills[key] ?? 1,
      to_level: saved?.target_skills[key] ?? track.max_level,
    }
  }
}

async function load() {
  loading.value = true
  message.value = ''
  try {
    profile.value = await getProgressionProfile(props.characterId)
    initializeTracks()
    if (auth.isAuthenticated) {
      try {
        const saved = await getSavedProgression(props.characterId)
        currentLevel.value = saved.current_level
        targetLevel.value = saved.target_level
        eidolon.value = saved.eidolon
        initializeTracks(saved)
      } catch (error) {
        if (!axios.isAxiosError(error) || error.response?.status !== 404) throw error
      }
    }
    await recalculate()
  } catch {
    message.value = '养成规则暂时无法载入。'
  } finally {
    loading.value = false
  }
}

async function recalculate() {
  if (!profile.value) return
  calculating.value = true
  message.value = ''
  try {
    result.value = await calculateProgression(props.characterId, {
      from_level: currentLevel.value,
      to_level: targetLevel.value,
      skill_ranges: Object.fromEntries(
        Object.entries(ranges).map(([key, value]) => [key, { ...value }]),
      ),
    })
  } catch (error) {
    message.value = axios.isAxiosError(error)
      ? String(error.response?.data?.detail ?? '材料计算失败。')
      : '材料计算失败。'
  } finally {
    calculating.value = false
  }
}

async function persist() {
  saving.value = true
  message.value = ''
  try {
    await saveProgression(props.characterId, {
      current_level: currentLevel.value,
      target_level: targetLevel.value,
      eidolon: eidolon.value,
      current_skills: Object.fromEntries(
        Object.entries(ranges).map(([key, value]) => [key, value.from_level]),
      ),
      target_skills: Object.fromEntries(
        Object.entries(ranges).map(([key, value]) => [key, value.to_level]),
      ),
    })
    message.value = '养成计划已保存到你的角色池。'
  } catch (error) {
    message.value = axios.isAxiosError(error)
      ? String(error.response?.data?.detail ?? '保存失败。')
      : '保存失败。'
  } finally {
    saving.value = false
  }
}

let timer = 0
watch(
  [currentLevel, targetLevel, () => JSON.stringify(ranges)],
  () => {
    window.clearTimeout(timer)
    timer = window.setTimeout(recalculate, 180)
  },
)
onMounted(load)
</script>

<template>
  <div v-if="loading" class="planner-state" aria-busy="true">正在读取养成规则…</div>
  <div v-else-if="profile" class="progression-planner">
    <header class="planner-header">
      <div>
        <span>PROGRESSION CALCULATOR</span>
        <h2>角色养成规划</h2>
        <p>仅统计等级晋阶与主技能，不包含经验书、升级过程信用点和行迹小节点。</p>
      </div>
      <button v-if="auth.isAuthenticated" type="button" :disabled="saving" @click="persist">
        {{ saving ? '保存中…' : '保存养成计划' }}
      </button>
      <router-link v-else to="/login">登录后保存</router-link>
    </header>

    <section class="range-panel">
      <div class="range-title">
        <h3>角色等级</h3>
        <b>Lv.{{ currentLevel }} → Lv.{{ targetLevel }}</b>
      </div>
      <label>当前等级<input v-model.number="currentLevel" type="range" min="1" :max="targetLevel" /></label>
      <label>目标等级<input v-model.number="targetLevel" type="range" :min="currentLevel" max="80" /></label>
      <label class="eidolon-field">当前星魂
        <select v-model.number="eidolon">
          <option v-for="value in 7" :key="value - 1" :value="value - 1">{{ value - 1 }} 魂</option>
        </select>
      </label>
    </section>

    <section class="skill-ranges">
      <article v-for="(track, key) in profile.tracks" :key="key">
        <div class="range-title"><h3>{{ track.label }}</h3><b>{{ ranges[key]?.from_level }} → {{ ranges[key]?.to_level }}</b></div>
        <label>From
          <input v-model.number="ranges[key].from_level" type="range" min="1" :max="ranges[key].to_level" />
        </label>
        <label>To
          <input v-model.number="ranges[key].to_level" type="range" :min="ranges[key].from_level" :max="track.max_level" />
        </label>
      </article>
    </section>

    <section>
      <div class="material-heading">
        <div><h3>所需材料</h3><p>材料卡片可进入物品档案。</p></div>
        <span v-if="calculating">计算中…</span>
      </div>
      <div class="material-grid">
        <router-link
          v-for="material in sortedMaterials"
          :key="material.key"
          :to="material.item ? `/items/${material.item.id}` : ''"
          class="material-card"
          :class="{ disabled: !material.item }"
        >
          <img v-if="material.item?.image_url" :src="material.item.image_url" :alt="material.item.name" />
          <div><small>{{ material.item?.name ?? material.key }}</small><b>×{{ material.quantity.toLocaleString() }}</b></div>
        </router-link>
      </div>
    </section>
    <p v-if="message" class="planner-message" role="status">{{ message }}</p>
  </div>
</template>

<style scoped>
.progression-planner { display: grid; gap: 1.5rem; }
.planner-header, .range-title, .material-heading { display: flex; justify-content: space-between; gap: 1rem; align-items: center; }
.planner-header span { color: var(--blue); font-size: .72rem; letter-spacing: .14em; }
.planner-header h2, .range-title h3, .material-heading h3 { margin: .3rem 0; }
.planner-header p, .material-heading p { margin: 0; color: var(--muted); }
.planner-header button, .planner-header a { border: 1px solid var(--gold); background: transparent; color: inherit; padding: .7rem 1rem; text-decoration: none; cursor: pointer; }
.range-panel, .skill-ranges article { background: var(--panel); border: 1px solid var(--line); padding: 1rem; }
.range-panel { display: grid; gap: .8rem; }
.range-panel label, .skill-ranges label { display: grid; gap: .35rem; color: var(--muted); font-size: .8rem; }
input[type="range"] { width: 100%; accent-color: var(--blue); }
.eidolon-field { max-width: 12rem; }
select { background: #0b1122; color: inherit; border: 1px solid var(--line); padding: .5rem; }
.skill-ranges { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; }
.skill-ranges article { display: grid; gap: .55rem; }
.range-title b { color: var(--blue); }
.material-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: .75rem; }
.material-card { display: flex; align-items: center; gap: .75rem; min-height: 72px; padding: .65rem; background: var(--panel); border: 1px solid var(--line); color: inherit; text-decoration: none; }
.material-card img { width: 52px; height: 52px; object-fit: contain; }
.material-card div { display: grid; gap: .25rem; }
.material-card b { color: var(--gold); }
.material-card.disabled { pointer-events: none; opacity: .65; }
.planner-message { border-left: 2px solid var(--gold); padding-left: .75rem; }
.planner-state { padding: 3rem; text-align: center; }
@media (max-width: 720px) {
  .planner-header { align-items: flex-start; flex-direction: column; }
  .skill-ranges { grid-template-columns: 1fr; }
}
</style>
