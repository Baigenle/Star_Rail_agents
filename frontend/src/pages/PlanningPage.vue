<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import AppShell from '../components/AppShell.vue'
import {
  calculateMultiProgression,
  deleteProgressionPlan,
  getCharacterPool,
  getProgressionPlans,
  getProgressionProfile,
  getSavedProgression,
  saveProgressionPlan,
  updateProgressionPlan,
} from '../services/api'
import type { UserCharacter } from '../types/profile'
import type {
  CharacterPlanInput,
  MultiProgressionResult,
  PlannerRow,
  ProgressionPlan,
} from '../types/planning'

const pool = ref<UserCharacter[]>([])
const rows = ref<Record<string, PlannerRow>>({})
const result = ref<MultiProgressionResult | null>(null)
const plans = ref<ProgressionPlan[]>([])
const planName = ref('本期角色养成')
const priority = ref(1)
const loading = ref(false)
const error = ref('')

const selectedRows = computed(() => Object.values(rows.value))

async function toggleCharacter(character: UserCharacter) {
  if (rows.value[character.character_id]) {
    const next = { ...rows.value }
    delete next[character.character_id]
    rows.value = next
    result.value = null
    return
  }
  error.value = ''
  try {
    const profile = await getProgressionProfile(character.character_id)
    let saved
    try {
      saved = await getSavedProgression(character.character_id)
    } catch {
      saved = null
    }
    const tracks = Object.fromEntries(
      Object.entries(profile.tracks).map(([key, track]) => [
        key,
        {
          label: track.label,
          maxLevel: track.max_level,
          from: saved?.current_skills[key] ?? 1,
          to: saved?.target_skills[key] ?? track.max_level,
        },
      ]),
    )
    rows.value = {
      ...rows.value,
      [character.character_id]: {
        character: {
          id: character.character_id,
          name: character.name,
          rarity: character.rarity,
          path: character.path,
          element: character.element,
          image_url: character.image_url,
        },
        fromLevel: saved?.current_level ?? character.level,
        toLevel: saved?.target_level ?? 80,
        tracks,
      },
    }
  } catch {
    error.value = `无法读取 ${character.name} 的养成规则。`
  }
}

function payload(): CharacterPlanInput[] {
  return selectedRows.value.map((row) => ({
    character_id: row.character.id,
    from_level: row.fromLevel,
    to_level: row.toLevel,
    skill_ranges: Object.fromEntries(
      Object.entries(row.tracks).map(([key, track]) => [
        key,
        { from_level: track.from, to_level: track.to },
      ]),
    ),
  }))
}

async function calculate() {
  if (!selectedRows.value.length) return
  loading.value = true
  error.value = ''
  try {
    result.value = await calculateMultiProgression(payload())
  } catch {
    error.value = '养成计算失败，请检查目标等级和技能区间。'
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!result.value || !planName.value.trim()) return
  const saved = await saveProgressionPlan({
    name: planName.value.trim(),
    priority: priority.value,
    characters: payload(),
  })
  plans.value = [saved, ...plans.value]
}

async function changeStatus(plan: ProgressionPlan, status: ProgressionPlan['status']) {
  const updated = await updateProgressionPlan(plan.id, { status })
  plans.value = plans.value.map((item) => (item.id === plan.id ? updated : item))
}

async function removePlan(plan: ProgressionPlan) {
  if (!window.confirm(`删除养成方案“${plan.name}”？该操作不会删除角色练度。`)) return
  await deleteProgressionPlan(plan.id)
  plans.value = plans.value.filter((item) => item.id !== plan.id)
}

function planPct(plan: ProgressionPlan): number {
  const progress = plan.progress
  if (!progress || progress.scheduled_runs <= 0) return 0
  return Math.min(Math.round((progress.completed_runs / progress.scheduled_runs) * 100), 100)
}

onMounted(async () => {
  loading.value = true
  try {
    const [characterPool, savedPlans] = await Promise.all([
      getCharacterPool(),
      getProgressionPlans(),
    ])
    pool.value = characterPool.items
    plans.value = savedPlans
  } catch {
    error.value = '角色池或已保存方案读取失败。'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <AppShell>
    <header class="planner-head">
      <div>
        <span class="eyebrow">CHARACTER BUILD AGENT</span>
        <h1>多角色养成规划</h1>
        <p>从当前练度到目标练度，合并相同材料，并只保留能验证的构筑建议。</p>
      </div>
      <router-link class="daily-entry" to="/weekly-plan">生成每周计划 →</router-link>
    </header>

    <section class="planner-panel">
      <div class="section-title"><div><small>STEP 01</small><h2>选择角色池成员</h2></div><span>{{ selectedRows.length }} / 12</span></div>
      <div class="pool-strip">
        <button
          v-for="character in pool"
          :key="character.character_id"
          type="button"
          :class="{ selected: rows[character.character_id] }"
          @click="toggleCharacter(character)"
        >
          <img :src="character.image_url || '/placeholder-character.svg'" :alt="character.name" />
          <span>{{ character.name }}</span>
          <small>Lv.{{ character.level }}</small>
        </button>
      </div>
      <p v-if="!pool.length && !loading" class="empty">请先在角色库批量导入你拥有的角色。</p>
    </section>

    <section v-if="selectedRows.length" class="target-grid">
      <article v-for="row in selectedRows" :key="row.character.id">
        <div class="target-character">
          <img :src="row.character.image_url || '/placeholder-character.svg'" :alt="row.character.name" />
          <div><strong>{{ row.character.name }}</strong><small>{{ row.character.element }} · {{ row.character.path }}</small></div>
        </div>
        <label>等级 {{ row.fromLevel }} → {{ row.toLevel }}</label>
        <div class="dual-range">
          <input v-model.number="row.fromLevel" type="range" min="1" :max="row.toLevel" />
          <input v-model.number="row.toLevel" type="range" :min="row.fromLevel" max="80" />
        </div>
        <details>
          <summary>技能目标（{{ Object.keys(row.tracks).length }} 项）</summary>
          <div v-for="(track, key) in row.tracks" :key="key" class="skill-target">
            <span>{{ track.label }}</span>
            <select v-model.number="track.from">
              <option v-for="level in track.maxLevel" :key="level" :value="level">{{ level }}</option>
            </select>
            <i>→</i>
            <select v-model.number="track.to">
              <option v-for="level in track.maxLevel" :key="level" :value="level" :disabled="level < track.from">{{ level }}</option>
            </select>
          </div>
        </details>
      </article>
    </section>

    <div class="planner-actions">
      <button type="button" :disabled="loading || !selectedRows.length" @click="calculate">
        {{ loading ? '黑塔计算中…' : '合并计算材料与构筑' }}
      </button>
      <span>经验书与升级过程信用点暂不计入。</span>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="result">
      <section class="result-panel">
        <div class="section-title"><div><small>STEP 02</small><h2>合并材料清单</h2></div><span>{{ result.materials.length }} 类</span></div>
        <div class="material-grid">
          <router-link
            v-for="material in result.materials"
            :key="material.key"
            :to="material.item ? `/items/${material.item.id}` : ''"
            class="material-card"
          >
            <img v-if="material.item?.image_url" :src="material.item.image_url" :alt="material.item.name" />
            <strong>{{ material.item?.name || material.key }}</strong>
            <b>×{{ material.quantity.toLocaleString() }}</b>
          </router-link>
        </div>
      </section>

      <section class="build-grid">
        <article v-for="row in selectedRows" :key="row.character.id">
          <h3>{{ row.character.name }} · 已验证构筑</h3>
          <div v-if="result.recommendations[row.character.id]">
            <p>光锥</p>
            <div class="recommend-strip">
              <router-link
                v-for="item in result.recommendations[row.character.id].lightcones"
                :key="item.id"
                :to="`/lightcones/${item.id}`"
              >{{ item.name }}</router-link>
            </div>
            <p>隧洞遗器</p>
            <div class="recommend-strip">
              <router-link
                v-for="item in result.recommendations[row.character.id].tunnel_relics"
                :key="item.id"
                :to="`/relics/${item.id}`"
              >{{ item.name }}</router-link>
            </div>
            <p>位面饰品</p>
            <div class="recommend-strip">
              <router-link
                v-for="item in result.recommendations[row.character.id].planar_relics"
                :key="item.id"
                :to="`/relics/${item.id}`"
              >{{ item.name }}</router-link>
            </div>
            <small v-for="warning in result.recommendations[row.character.id].warnings" :key="warning">{{ warning }}</small>
          </div>
        </article>
      </section>

      <section class="save-plan">
        <input v-model="planName" aria-label="方案名称" maxlength="80" />
        <label>优先级 <input v-model.number="priority" type="number" min="1" max="99" /></label>
        <button type="button" @click="save">保存养成方案</button>
      </section>
      <div class="protocol-card">
        <strong>Claim → Citation → Validation → Filtering</strong>
        <span>{{ result.response.validation.notes.join(' ') }}</span>
      </div>
    </template>

    <section class="saved-plans">
      <div class="section-title"><div><small>MEMORY</small><h2>已保存方案</h2></div><span>{{ plans.length }} 份</span></div>
      <article v-for="plan in plans" :key="plan.id">
        <div class="plan-row">
          <div><strong>{{ plan.name }}</strong><small>优先级 {{ plan.priority }} · {{ plan.status }}</small></div>
          <div>
            <button v-if="plan.status !== 'active'" type="button" @click="changeStatus(plan, 'active')">启用</button>
            <button v-if="plan.status === 'active'" type="button" @click="changeStatus(plan, 'paused')">暂停</button>
            <button v-if="plan.status !== 'completed'" type="button" @click="changeStatus(plan, 'completed')">完成</button>
            <button class="danger" type="button" @click="removePlan(plan)">删除</button>
          </div>
        </div>
        <div class="plan-progress">
          <template v-if="plan.progress?.in_current_window">
            <div class="bar"><i :style="{ width: planPct(plan) + '%' }"></i></div>
            <small>
              本周已完成 {{ plan.progress.completed_runs }} / {{ plan.progress.scheduled_runs }} 次
              <b v-if="plan.progress.complete" class="ok">· 本周方案已完成 ✓</b>
              <b v-else>· 进行中</b>
            </small>
          </template>
          <small v-else class="not-scheduled">未排入本周计划 — 到「每周规划」生成后自动跟随执行</small>
        </div>
      </article>
    </section>
  </AppShell>
</template>

<style scoped>
.planner-head { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-bottom: 24px; }
.planner-head h1 { margin: 5px 0; }
.planner-head p, .planner-actions span { color: var(--muted); }
.daily-entry { padding: 11px 16px; border-radius: 999px; color: #282219; background: var(--gold); font-weight: 700; }
.planner-panel, .result-panel, .saved-plans { padding: 20px; margin-bottom: 18px; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); }
.saved-plans article { display: grid; gap: 12px; padding: 15px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); }
.saved-plans article + article { margin-top: 10px; }
.plan-row { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
.plan-row > div:last-child { display: flex; gap: 8px; flex-wrap: wrap; }
.plan-row button { padding: 8px 12px; border: 1px solid var(--line); border-radius: var(--radius-md); color: var(--text-secondary); background: var(--surface-muted); cursor: pointer; }
.plan-row button.danger { color: var(--danger); }
.plan-progress { display: grid; gap: 6px; }
.plan-progress .bar { height: 8px; border-radius: 999px; background: var(--line); overflow: hidden; }
.plan-progress .bar i { display: block; height: 100%; border-radius: 999px; background: var(--gold); transition: width .8s cubic-bezier(.22, 1, .36, 1); }
.plan-progress small { color: var(--muted); }
.plan-progress b.ok { color: var(--success); }
.not-scheduled { color: var(--muted); }
.section-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.section-title h2 { margin: 3px 0; }
.section-title small { color: var(--accent-text); letter-spacing: .14em; }
.pool-strip { display: grid; grid-auto-flow: column; grid-auto-columns: 108px; grid-template-columns: none; gap: 9px; padding-bottom: 6px; overflow-x: auto; overflow-y: hidden; overscroll-behavior-inline: contain; }
.pool-strip button { display: grid; justify-items: center; gap: 5px; padding: 10px; border: 1px solid var(--line); border-radius: var(--radius-lg); color: var(--text-secondary); background: var(--surface); cursor: pointer; }
.pool-strip button.selected { border-color: var(--line-strong); box-shadow: inset 0 0 0 1px rgba(233, 200, 117, .2); background: color-mix(in srgb, var(--gold) 10%, var(--surface)); }
.pool-strip img { width: 72px; height: 72px; object-fit: contain; }
.pool-strip small, .target-character small { color: var(--muted); }
.target-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; }
.target-grid article, .build-grid article { padding: 17px; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); }
.target-character { display: flex; gap: 12px; align-items: center; margin-bottom: 15px; }
.target-character img { width: 58px; height: 58px; object-fit: contain; border-radius: var(--radius-md); background: var(--page-soft); }
.target-character div { display: grid; gap: 4px; }
.dual-range { display: grid; gap: 6px; margin: 9px 0 14px; }
input[type='range'] { accent-color: var(--gold); }
details summary { color: var(--accent-text); cursor: pointer; }
.skill-target { display: grid; grid-template-columns: minmax(110px, 1fr) 62px 20px 62px; gap: 7px; align-items: center; margin-top: 9px; }
.skill-target select, .save-plan input { min-width: 0; padding: 8px; border: 1px solid var(--line); border-radius: var(--radius-md); color: var(--text); background: var(--surface); }
.skill-target i { color: var(--muted); font-style: normal; text-align: center; }
.planner-actions { display: flex; gap: 15px; align-items: center; margin: 18px 0 26px; }
.planner-actions button, .save-plan button, .saved-plans button { padding: 10px 15px; border: 0; border-radius: var(--radius-md); color: #282219; background: var(--gold); font-weight: 700; cursor: pointer; }
.planner-actions button:disabled { opacity: .5; }
.material-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(145px, 1fr)); gap: 10px; }
.material-card { display: grid; grid-template-columns: 45px 1fr; gap: 4px 9px; align-items: center; padding: 10px; border-radius: var(--radius-lg); color: var(--text-secondary); background: var(--surface); }
.material-card img { grid-row: span 2; width: 45px; height: 45px; object-fit: contain; }
.material-card b { color: var(--accent-text); }
.build-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; margin: 18px 0; }
.recommend-strip { display: flex; flex-wrap: wrap; gap: 7px; }
.recommend-strip a { padding: 7px 9px; border-radius: var(--radius-md); color: var(--text-secondary); background: var(--surface-muted); }
.build-grid small { display: block; margin-top: 8px; color: #c58e8e; }
.save-plan { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 18px 0; }
.save-plan > input { min-width: 260px; }
.save-plan label input { width: 64px; }
.protocol-card { display: grid; gap: 5px; padding: 15px; border-left: 3px solid var(--gold); background: rgba(233, 200, 117, .08); }
.protocol-card span { color: var(--muted); }
.saved-plans article { display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 12px; border-top: 1px solid #272034; }
.saved-plans article > div { display: flex; gap: 8px; align-items: center; }
.saved-plans small { color: #837c94; }
.saved-plans button.danger { color: #ffdce2; background: #7b3140; }
@media (max-width: 760px) { .planner-head, .saved-plans article { align-items: start; flex-direction: column; } }
</style>
