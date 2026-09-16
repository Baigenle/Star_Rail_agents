<script setup lang="ts">
import axios from 'axios'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import {
  deleteSavedTeam,
  getCharacterPool,
  getCharacters,
  getSavedTeams,
  recommendOfficialTeams,
  renameSavedTeam,
  saveOfficialTeam,
} from '../services/api'
import type { CharacterSummary } from '../types/catalog'
import type { CharacterPool } from '../types/profile'
import type { OfficialTeamResult, RecommendedOfficialTeam, SavedTeam } from '../types/team'

const route = useRoute()
const characters = ref<CharacterSummary[]>([])
const pool = ref<CharacterPool>({ items: [], total: 0, favorites: 0 })
const savedTeams = ref<SavedTeam[]>([])
const result = ref<OfficialTeamResult | null>(null)
const coreId = ref('')
const preferredIds = ref<string[]>([])
const excludedIds = ref<string[]>([])
const preferenceQuery = ref('')
const exclusionQuery = ref('')
const requireSustain = ref(true)
const useOwnedOnly = ref(false)
const gameMode = ref<'balanced' | 'moc' | 'pure_fiction' | 'apocalyptic'>('balanced')
const gameModes = [
  { value: 'balanced', label: '综合', hint: '三种场景均衡考虑' },
  { value: 'moc', label: '混沌回忆', hint: '偏重单体 Boss 对决' },
  { value: 'pure_fiction', label: '虚构叙事', hint: '偏重群体清场' },
  { value: 'apocalyptic', label: '末日幻影', hint: '偏重单体 Boss 硬拼' },
] as const
const busy = ref(false)
const error = ref('')
const excludedIncompleteIds = new Set(['1508', '1509'])
const ownedIdSet = computed(() => new Set(pool.value.items.map((item) => item.character_id)))
const favoriteIdSet = computed(() => new Set(
  pool.value.items.filter((item) => item.is_favorite).map((item) => item.character_id),
))

const coreOptions = computed(() =>
  useOwnedOnly.value
    ? characters.value.filter((character) => (
      !excludedIncompleteIds.has(character.id)
      && pool.value.items.some((item) => item.character_id === character.id)
    ))
    : characters.value.filter((character) => !excludedIncompleteIds.has(character.id)),
)
const preferenceOptions = computed(() => characters.value
  .filter((character) => !excludedIncompleteIds.has(character.id))
  .sort((left, right) => {
  const ownedDifference = Number(ownedIdSet.value.has(right.id)) - Number(ownedIdSet.value.has(left.id))
  if (ownedDifference) return ownedDifference
  return right.rarity - left.rarity || left.name.localeCompare(right.name, 'zh-CN')
}))
const visiblePreferenceOptions = computed(() => {
  const query = preferenceQuery.value.trim().toLocaleLowerCase('zh-CN')
  if (query) {
    return preferenceOptions.value.filter((character) => (
      character.name.toLocaleLowerCase('zh-CN').includes(query)
    ))
  }
  return preferenceOptions.value.filter((character) => (
    ownedIdSet.value.has(character.id) || preferredIds.value.includes(character.id)
  ))
})
const visibleExclusionOptions = computed(() => {
  const query = exclusionQuery.value.trim().toLocaleLowerCase('zh-CN')
  if (query) {
    return preferenceOptions.value.filter((character) => (
      character.name.toLocaleLowerCase('zh-CN').includes(query)
    ))
  }
  return preferenceOptions.value.filter((character) => excludedIds.value.includes(character.id))
})

function errorMessage(reason: unknown): string {
  return axios.isAxiosError(reason)
    ? String(reason.response?.data?.detail ?? '配队请求失败。')
    : '配队请求失败。'
}

onMounted(async () => {
  try {
    const [catalog, owned, teams] = await Promise.all([
      getCharacters(),
      getCharacterPool(),
      getSavedTeams(),
    ])
    characters.value = catalog
    pool.value = owned
    savedTeams.value = teams
    const prefillName = String(route.query.core ?? '').trim()
    const prefill = prefillName
      ? catalog.find((item) => item.name === prefillName)
      : undefined
    coreId.value = prefill?.id
      ?? owned.items.find((item) => item.is_favorite)?.character_id
      ?? owned.items[0]?.character_id
      ?? catalog[0]?.id
      ?? ''
    preferredIds.value = owned.items
      .filter((item) => item.is_favorite && !excludedIncompleteIds.has(item.character_id))
      .map((item) => item.character_id)
  } catch (reason) {
    error.value = errorMessage(reason)
  }
})

async function generate() {
  if (!coreId.value) return
  busy.value = true
  error.value = ''
  try {
    result.value = await recommendOfficialTeams({
      core_character_id: coreId.value,
      preferred_character_ids: preferredIds.value.filter((id) => id !== coreId.value),
      excluded_character_ids: excludedIds.value.filter((id) => id !== coreId.value),
      require_sustain: requireSustain.value,
      use_owned_only: useOwnedOnly.value,
      game_mode: gameMode.value,
    })
  } catch (reason) {
    error.value = errorMessage(reason)
  } finally {
    busy.value = false
  }
}

function togglePreferred(characterId: string) {
  preferredIds.value = preferredIds.value.includes(characterId)
    ? preferredIds.value.filter((id) => id !== characterId)
    : [...preferredIds.value, characterId]
  excludedIds.value = excludedIds.value.filter((id) => id !== characterId)
}

function toggleExcluded(characterId: string) {
  excludedIds.value = excludedIds.value.includes(characterId)
    ? excludedIds.value.filter((id) => id !== characterId)
    : [...excludedIds.value, characterId]
  preferredIds.value = preferredIds.value.filter((id) => id !== characterId)
}

function characterName(characterId: string) {
  return characters.value.find((item) => item.id === characterId)?.name ?? characterId
}

function speedOrder(team: RecommendedOfficialTeam) {
  return team.rotation?.speed_order.map(characterName).join(' → ') ?? '数据不足'
}

async function save(team: RecommendedOfficialTeam) {
  const defaultName = `${team.members[0]?.name ?? '核心'}队`
  const name = window.prompt('给这支常用队伍起个名字', defaultName)?.trim()
  if (!name) return
  try {
    const saved = await saveOfficialTeam(name, team.members.map((member) => member.character_id))
    savedTeams.value = [saved, ...savedTeams.value]
  } catch (reason) {
    error.value = errorMessage(reason)
  }
}

async function remove(team: SavedTeam) {
  if (!window.confirm(`删除常用队伍“${team.name}”？`)) return
  await deleteSavedTeam(team.id)
  savedTeams.value = savedTeams.value.filter((item) => item.id !== team.id)
}

async function rename(team: SavedTeam) {
  const name = window.prompt('修改常用队伍名称', team.name)?.trim()
  if (!name || name === team.name) return
  try {
    const updated = await renameSavedTeam(team.id, name)
    savedTeams.value = savedTeams.value.map((item) => (
      item.id === team.id ? updated : item
    ))
  } catch (reason) {
    error.value = errorMessage(reason)
  }
}
</script>

<template>
  <AppShell>
    <header class="team-header">
      <div>
        <span class="eyebrow">TEAM RECOMMENDATION AGENT</span>
        <h1>官方角色智能配队</h1>
        <p>先按角色池、定位、机制标签和历史配队确定候选，再由推理模型逐队复核协同与限制。</p>
      </div>
      <router-link to="/characters">管理我的角色池</router-link>
    </header>

    <section class="team-controls">
      <label class="core-control">核心角色
        <select v-model="coreId">
          <option v-for="character in coreOptions" :key="character.id" :value="character.id">
            {{ character.name }} · {{ character.element }} · {{ character.path }}
          </option>
        </select>
      </label>
      <div class="game-mode-picker" role="radiogroup" aria-label="游戏模式">
        <button
          v-for="mode in gameModes"
          :key="mode.value"
          type="button"
          :class="{ active: gameMode === mode.value }"
          :title="mode.hint"
          @click="gameMode = mode.value"
        >
          {{ mode.label }}
        </button>
      </div>
      <div class="team-toggles">
        <label><input v-model="requireSustain" type="checkbox" /> 必须包含生存位</label>
        <label><input v-model="useOwnedOnly" type="checkbox" /> 只生成我的角色队</label>
      </div>
      <button class="generate-team" :disabled="busy || !coreId" @click="generate">{{ busy ? '黑塔正在计算…' : '生成配队' }}</button>
      <div class="picker-grid">
        <details class="preference-picker">
          <summary>
            <span><b>偏好角色</b><small>仅用于额外的猜你喜欢方案，不改变基础评分</small></span>
            <em>{{ preferredIds.length }} 已选</em>
          </summary>
          <div class="picker-body">
            <input v-model.trim="preferenceQuery" type="search" placeholder="搜索角色；默认只显示已拥有角色" />
            <div v-if="preferredIds.length" class="selected-characters">
              <button v-for="id in preferredIds" :key="`selected-prefer-${id}`" type="button" @click="togglePreferred(id)">
                {{ characterName(id) }} ×
              </button>
            </div>
            <div class="choice-grid">
              <button
                v-for="character in visiblePreferenceOptions"
                :key="`prefer-${character.id}`"
                type="button"
                :class="{ active: preferredIds.includes(character.id) }"
                :aria-pressed="preferredIds.includes(character.id)"
                @click="togglePreferred(character.id)"
              >
                <span v-if="favoriteIdSet.has(character.id)">♥</span>
                {{ character.name }}
                <small>{{ ownedIdSet.has(character.id) ? '已拥有' : '未拥有' }}</small>
              </button>
            </div>
            <p v-if="!visiblePreferenceOptions.length">没有匹配角色，请输入其他名称。</p>
          </div>
        </details>
        <details class="preference-picker exclude-picker">
          <summary>
            <span><b>排除角色</b><small>仅在需要时搜索并添加，不再铺开全角色列表</small></span>
            <em>{{ excludedIds.length }} 已选</em>
          </summary>
          <div class="picker-body">
            <input v-model.trim="exclusionQuery" type="search" placeholder="输入要排除的角色名称" />
            <div v-if="excludedIds.length" class="selected-characters">
              <button v-for="id in excludedIds" :key="`selected-exclude-${id}`" type="button" @click="toggleExcluded(id)">
                {{ characterName(id) }} ×
              </button>
            </div>
            <div class="choice-grid">
              <button
                v-for="character in visibleExclusionOptions"
                :key="`exclude-${character.id}`"
                type="button"
                :class="{ active: excludedIds.includes(character.id) }"
                :aria-pressed="excludedIds.includes(character.id)"
                @click="toggleExcluded(character.id)"
              >
                {{ character.name }}
              </button>
            </div>
            <p v-if="!visibleExclusionOptions.length">输入角色名后再选择，当前不会排除任何角色。</p>
          </div>
        </details>
      </div>
    </section>

    <p v-if="error" class="catalog-state error" role="alert">{{ error }}</p>

    <template v-if="result">
      <section v-if="result.owned.length" class="team-section">
        <div class="section-title"><div><span>OWNED</span><h2>我的角色池可用队</h2></div><small>可以保存为常用队伍</small></div>
        <div class="team-grid">
          <article v-for="team in result.owned" :key="`owned-${team.members.map((member) => member.character_id).join('-')}`" class="team-card">
            <b>{{ team.score }} 综合分</b>
            <div class="member-row">
              <router-link v-for="member in team.members" :key="member.character_id" :to="`/characters/${member.character_id}`">
                <img v-if="member.image_url" :src="member.image_url" :alt="member.name" />
                <span>{{ member.name }}</span><small>{{ member.element }}</small>
              </router-link>
            </div>
            <p>{{ team.reasons.join('；') }}</p>
            <div v-if="team.score_breakdown" class="score-breakdown">
              <div class="score-metrics">
                <span>机制模拟 <b>{{ team.score_breakdown.mechanical_simulation_score }}</b></span>
                <span>证据置信 <b>{{ team.score_breakdown.evidence_confidence }}</b></span>
                <span>实战先验 <b>{{ team.score_breakdown.observed_meta_score ?? '待补充' }}</b></span>
                <span>数据版本 <b>{{ team.score_breakdown.game_data_version }}</b></span>
              </div>
              <div class="scenario-grid">
                <span v-for="scenario in team.score_breakdown.scenarios" :key="scenario.scenario_id">
                  {{ scenario.name }} <b>{{ scenario.score }}</b>
                </span>
              </div>
            </div>
            <p v-if="team.model_assessment" class="model-assessment"><b>模型复核：</b>{{ team.model_assessment }}</p>
            <ul><li v-for="item in team.strengths" :key="item">{{ item }}</li></ul>
            <details>
              <summary>轮转与数据限制</summary>
              <p>战技点净变化：{{ team.rotation?.skill_point_balance ?? '未知' }}</p>
              <p>速度顺序：{{ speedOrder(team) }}</p>
              <p>{{ team.weaknesses.join('；') }}</p>
              <p v-for="warning in team.data_warnings" :key="warning" class="data-warning">{{ warning }}</p>
            </details>
            <button @click="save(team)">保存为常用队伍</button>
          </article>
        </div>
      </section>

      <section v-if="result.theoretical.length" class="team-section">
        <div class="section-title"><div><span>THEORETICAL</span><h2>理论推荐队</h2></div><small>可能包含尚未拥有的角色</small></div>
        <div class="team-grid">
          <article v-for="team in result.theoretical" :key="team.members.map((member) => member.character_id).join('-')" class="team-card">
            <b>{{ team.score }} 综合分</b>
            <span v-if="team.missing_character_ids.length" class="missing-badge">
              缺少 {{ team.missing_character_ids.map(characterName).join('、') }}
            </span>
            <div class="member-row">
              <router-link v-for="member in team.members" :key="member.character_id" :to="`/characters/${member.character_id}`">
                <img v-if="member.image_url" :src="member.image_url" :alt="member.name" />
                <span>{{ member.name }}</span><small>{{ member.element }}</small>
              </router-link>
            </div>
            <p>{{ team.reasons.join('；') }}</p>
            <div v-if="team.score_breakdown" class="score-breakdown">
              <div class="score-metrics">
                <span>机制模拟 <b>{{ team.score_breakdown.mechanical_simulation_score }}</b></span>
                <span>证据置信 <b>{{ team.score_breakdown.evidence_confidence }}</b></span>
                <span>实战先验 <b>{{ team.score_breakdown.observed_meta_score ?? '待补充' }}</b></span>
              </div>
              <div class="scenario-grid">
                <span v-for="scenario in team.score_breakdown.scenarios" :key="scenario.scenario_id">
                  {{ scenario.name }} <b>{{ scenario.score }}</b>
                </span>
              </div>
            </div>
            <p v-if="team.model_assessment" class="model-assessment"><b>模型复核：</b>{{ team.model_assessment }}</p>
            <details><summary>轮转与数据限制</summary><p>速度顺序：{{ speedOrder(team) }}</p><p v-for="warning in team.data_warnings" :key="warning" class="data-warning">{{ warning }}</p></details>
          </article>
        </div>
      </section>
      <section v-if="result.favorite_trials.length" class="team-section">
        <div class="section-title"><div><span>FAVORITE TRIALS</span><h2>猜你喜欢尝试队</h2></div><small>偏好不计分，只在结构合格时尝试加入</small></div>
        <div class="team-grid">
          <article v-for="team in result.favorite_trials" :key="`favorite-${team.members.map((member) => member.character_id).join('-')}`" class="team-card favorite-card">
            <b>{{ team.score }} 综合分 · 偏好不加分</b>
            <span v-if="team.missing_character_ids.length" class="missing-badge">
              缺少 {{ team.missing_character_ids.map(characterName).join('、') }}
            </span>
            <div class="member-row">
              <router-link v-for="member in team.members" :key="member.character_id" :to="`/characters/${member.character_id}`">
                <img v-if="member.image_url" :src="member.image_url" :alt="member.name" />
                <span>{{ favoriteIdSet.has(member.character_id) ? '♥ ' : '' }}{{ member.name }}</span><small>{{ member.element }}</small>
              </router-link>
            </div>
            <p>{{ team.reasons.join('；') }}</p>
            <div v-if="team.score_breakdown" class="score-breakdown">
              <div class="score-metrics">
                <span>机制模拟 <b>{{ team.score_breakdown.mechanical_simulation_score }}</b></span>
                <span>证据置信 <b>{{ team.score_breakdown.evidence_confidence }}</b></span>
                <span>实战先验 <b>{{ team.score_breakdown.observed_meta_score ?? '待补充' }}</b></span>
              </div>
              <div class="scenario-grid">
                <span v-for="scenario in team.score_breakdown.scenarios" :key="scenario.scenario_id">
                  {{ scenario.name }} <b>{{ scenario.score }}</b>
                </span>
              </div>
            </div>
            <p v-if="team.model_assessment" class="model-assessment"><b>模型复核：</b>{{ team.model_assessment }}</p>
            <details><summary>轮转与数据限制</summary><p>速度顺序：{{ speedOrder(team) }}</p><p v-for="warning in team.data_warnings" :key="warning" class="data-warning">{{ warning }}</p></details>
          </article>
        </div>
      </section>
      <details class="protocol"><summary>Claim → Citation → Validation → Filtering</summary><pre>{{ JSON.stringify(result.response, null, 2) }}</pre></details>
    </template>

    <section class="team-section saved-section">
      <div class="section-title"><div><span>MEMORY</span><h2>已保存的常用队伍</h2></div><small>{{ savedTeams.length }} 支</small></div>
      <div v-if="savedTeams.length" class="saved-grid">
        <article v-for="team in savedTeams" :key="team.id">
          <div><h3>{{ team.name }}</h3><p>{{ team.members.map((member) => member.name).join(' · ') }}</p></div>
          <div class="saved-actions">
            <button @click="rename(team)">改名</button>
            <button @click="remove(team)">删除</button>
          </div>
        </article>
      </div>
      <p v-else class="catalog-state">还没有保存常用队伍。</p>
    </section>
  </AppShell>
</template>

<style scoped>
.team-header, .section-title, .saved-grid article { display: flex; justify-content: space-between; gap: 1rem; align-items: center; }
.team-header p, .team-card p, .section-title small, .saved-grid p { color: var(--muted); }
.team-controls { display: grid; grid-template-columns: minmax(260px, 1fr) minmax(220px, .7fr) auto; gap: 1rem; align-items: end; margin: 1.5rem 0; padding: 1rem; border: 1px solid var(--line); background: var(--panel); }
.team-controls label { display: grid; gap: .45rem; color: var(--muted); font-size: .8rem; }
.team-controls select { min-height: 2.8rem; padding: .65rem; border: 1px solid var(--line); color: var(--text); background: var(--surface); }
.team-controls button, .team-card button, .saved-grid button { border: 1px solid var(--gold); padding: .7rem 1rem; color: #edf2ff; background: rgba(230,201,130,.12); cursor: pointer; }
.generate-team { min-height: 2.8rem; color: #29231a !important; background: var(--gold) !important; font-weight: 700; }
.picker-grid { grid-column: 1 / -1; display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; align-items: start; }
.preference-picker { min-width: 0; margin: 0; border: 1px solid var(--line); background: var(--surface); }
.preference-picker summary { display: flex; gap: 1rem; align-items: center; justify-content: space-between; min-height: 62px; padding: .75rem .85rem; cursor: pointer; list-style-position: inside; }
.preference-picker summary > span { display: grid; gap: .2rem; }
.preference-picker summary b { color: var(--text); font-size: .85rem; }
.preference-picker summary small { color: var(--muted); font-size: .68rem; font-weight: 400; }
.preference-picker summary em { flex: 0 0 auto; color: var(--accent-text); font-size: .7rem; font-style: normal; }
.picker-body { display: grid; gap: .65rem; padding: 0 .75rem .75rem; border-top: 1px solid var(--line); }
.picker-body > input { width: 100%; min-height: 2.5rem; margin-top: .75rem; padding: .55rem .7rem; border: 1px solid var(--line); color: var(--text); background: var(--page-soft); }
.preference-picker p { margin: 0; color: var(--muted); font-size: .7rem; }
.selected-characters { display: flex; flex-wrap: wrap; gap: .35rem; }
.selected-characters button { padding: .35rem .5rem; color: var(--text-secondary); border-color: var(--line); background: var(--surface-muted); font-size: .7rem; }
.choice-grid { display: flex; flex-wrap: wrap; align-content: flex-start; gap: .4rem; max-height: 10rem; overflow-y: auto; }
.choice-grid button { display: inline-flex; align-items: center; gap: .3rem; padding: .45rem .55rem; color: var(--text-secondary); border-color: var(--line); font-size: .75rem; background: var(--page-soft); }
.choice-grid button.active { border-color: var(--gold); color: #17111f; background: var(--gold); }
.choice-grid button small { color: var(--muted); font-size: .6rem; }
.choice-grid button.active small { color: #493b20; }
.exclude-picker .choice-grid button.active { border-color: #d57b8c; color: #fff; background: rgba(168, 54, 75, .7); }
.game-mode-picker { display: flex; flex-wrap: wrap; gap: .45rem; align-content: center; }
.game-mode-picker button { padding: .4rem .8rem; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); color: var(--text); font: inherit; font-size: .88rem; cursor: pointer; }
.game-mode-picker button.active { border-color: var(--gold); color: var(--gold); }
.team-toggles { display: grid; align-content: center; gap: .6rem; }
.team-toggles label { display: flex; align-items: center; gap: .45rem; }
.team-section { margin-top: 2rem; }
.section-title span { color: var(--gold); font-size: .72rem; letter-spacing: .14em; }
.section-title h2 { margin: .25rem 0; }
.team-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 1rem; }
.team-card { padding: 1rem; border: 1px solid var(--line); background: var(--panel); }
.team-card > b { color: var(--gold); }
.missing-badge { float: right; padding: .3rem .55rem; color: #efb4be; background: rgba(153, 53, 74, .2); font-size: .7rem; }
.member-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: .5rem; margin: 1rem 0; }
.member-row a { display: grid; justify-items: center; gap: .25rem; padding: .5rem; border: 1px solid var(--line); color: inherit; text-decoration: none; }
.member-row img { width: 64px; height: 64px; object-fit: contain; }
.member-row small { color: var(--muted); }
.team-card li { margin: .35rem 0; color: #bdc9df; }
.model-assessment { padding: .75rem; border-left: 2px solid var(--gold); background: rgba(230,201,130,.06); }
.score-breakdown { display: grid; gap: .65rem; margin: .85rem 0; padding: .75rem; border: 1px solid rgba(132, 159, 208, .25); background: rgba(11, 19, 35, .72); }
.score-metrics, .scenario-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(112px, 1fr)); gap: .45rem; }
.score-metrics span, .scenario-grid span { display: grid; gap: .2rem; padding: .45rem; color: var(--muted); background: rgba(255, 255, 255, .025); font-size: .7rem; }
.score-metrics b, .scenario-grid b { color: #e7edf9; font-size: .9rem; }
.data-warning { color: #e9b98f !important; font-size: .75rem; }
.favorite-card { border-color: rgba(230,201,130,.35); }
.protocol { margin: 1rem 0; padding: 1rem; border: 1px solid var(--line); }
.protocol pre { max-height: 22rem; overflow: auto; white-space: pre-wrap; }
.saved-grid { display: grid; gap: .6rem; }
.saved-grid article { padding: .8rem 1rem; border: 1px solid var(--line); background: var(--panel); }
.saved-grid h3, .saved-grid p { margin: .2rem 0; }
.saved-actions { display: flex; gap: .5rem; }
.error { color: #ff9b9b; }
@media (max-width: 900px) { .team-controls, .picker-grid { grid-template-columns: 1fr; } .team-grid { grid-template-columns: 1fr; } }
</style>
