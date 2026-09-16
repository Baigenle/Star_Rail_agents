<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import KnowledgeTabs from '../components/KnowledgeTabs.vue'
import {
  getCharacterPool,
  getCharacters,
  replaceCharacterPool,
  setCharacterFavorite,
} from '../services/api'
import { useAuthStore } from '../stores/auth'
import type { CharacterSummary } from '../types/catalog'
import type { UserCharacter } from '../types/profile'

const auth = useAuthStore()
const router = useRouter()
const characters = ref<CharacterSummary[]>([])
const pool = ref<UserCharacter[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const notice = ref('')
const search = ref('')
const element = ref('全部')
const path = ref('全部')
const rarity = ref('全部')
const ownership = ref('全部角色')
const editMode = ref(false)
const draftIds = ref(new Set<string>())
const elements = ['全部', '物理', '火', '冰', '雷', '风', '量子', '虚数']
const paths = ['全部', '毁灭', '巡猎', '智识', '同谐', '虚无', '存护', '丰饶', '记忆', '欢愉']
const normalizeSearchText = (value: string) => value
  .normalize('NFKC')
  .replace(/[^\u4e00-\u9fffA-Za-z0-9]+/g, '')
  .toLowerCase()

const ownedIds = computed(() => new Set(pool.value.map((item) => item.character_id)))
const favoriteIds = computed(() => new Set(
  pool.value.filter((item) => item.is_favorite).map((item) => item.character_id),
))
const selectedIds = computed(() => editMode.value ? draftIds.value : ownedIds.value)
const filtered = computed(() => characters.value.filter((item) => {
  const query = normalizeSearchText(search.value.trim())
  const matchesOwnership = ownership.value === '全部角色'
    || (ownership.value === '已拥有' && selectedIds.value.has(item.id))
    || (ownership.value === '喜欢' && favoriteIds.value.has(item.id))
  return (!query || normalizeSearchText(item.name).includes(query))
    && (element.value === '全部' || item.element === element.value)
    && (path.value === '全部' || item.path === path.value)
    && (rarity.value === '全部' || item.rarity === Number(rarity.value))
    && matchesOwnership
}))

function beginImport() {
  notice.value = ''
  error.value = ''
  if (!auth.isAuthenticated) {
    router.push({ name: 'login', query: { redirect: '/characters' } })
    return
  }
  draftIds.value = new Set(ownedIds.value)
  editMode.value = true
}

function cancelImport() {
  editMode.value = false
  draftIds.value = new Set()
}

function toggleSelection(characterId: string) {
  if (!editMode.value) return
  const next = new Set(draftIds.value)
  if (next.has(characterId)) next.delete(characterId)
  else next.add(characterId)
  draftIds.value = next
}

function selectFiltered() {
  draftIds.value = new Set([...draftIds.value, ...filtered.value.map((item) => item.id)])
}

function clearSelection() {
  draftIds.value = new Set()
}

async function saveImport() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await replaceCharacterPool([...draftIds.value])
    pool.value = result.items
    editMode.value = false
    notice.value = `已保存 ${result.total} 名角色，其中 ${result.favorites} 名标记为喜欢。`
  } catch (reason) {
    error.value = auth.errorMessage(reason)
  } finally {
    saving.value = false
  }
}

async function toggleFavorite(characterId: string) {
  const current = pool.value.find((item) => item.character_id === characterId)
  if (!current) return
  error.value = ''
  notice.value = ''
  try {
    const updated = await setCharacterFavorite(characterId, !current.is_favorite)
    pool.value = pool.value.map((item) => (
      item.character_id === characterId ? updated : item
    ))
    notice.value = updated.is_favorite
      ? `已将 ${updated.name} 标记为喜欢。`
      : `已取消 ${updated.name} 的喜欢标记。`
  } catch (reason) {
    error.value = auth.errorMessage(reason)
  }
}

onMounted(async () => {
  try {
    if (auth.token) await auth.refresh()
    const [catalog, characterPool] = await Promise.all([
      getCharacters(),
      auth.isAuthenticated ? getCharacterPool() : Promise.resolve(null),
    ])
    characters.value = catalog
    if (characterPool) pool.value = characterPool.items
  } catch (reason) {
    error.value = auth.errorMessage(reason)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <AppShell>
    <KnowledgeTabs />
    <header class="catalog-header">
      <div>
        <span class="eyebrow">CHARACTER ARCHIVE</span>
        <h1>角色智库</h1>
        <p>批量建立你的角色池，供后续配队推荐和养成规划调用。</p>
      </div>
      <div class="archive-actions">
        <span class="archive-count">{{ filtered.length }} / {{ characters.length }} 份档案</span>
        <button class="pool-primary" type="button" @click="beginImport">
          {{ auth.isAuthenticated ? '批量导入角色' : '登录后建立角色池' }}
        </button>
      </div>
    </header>

    <section v-if="auth.isAuthenticated" class="pool-summary" aria-label="我的角色池摘要">
      <div><small>MY ROSTER</small><strong>{{ pool.length }}</strong><span>已拥有</span></div>
      <div><small>FAVORITES</small><strong>{{ favoriteIds.size }}</strong><span>喜欢角色</span></div>
      <p>角色池会保存到你的账户中，之后可直接提供给配队 Agent 与养成 Agent。</p>
    </section>

    <section v-if="editMode" class="pool-editor">
      <div>
        <span class="eyebrow">BATCH IMPORT</span>
        <strong>已选择 {{ draftIds.size }} 名角色</strong>
        <p>点击角色卡片进行多选。再次保存时会以本次选择覆盖“我的角色”。</p>
      </div>
      <div class="pool-editor-actions">
        <button type="button" @click="selectFiltered">选择当前结果</button>
        <button type="button" @click="clearSelection">清空</button>
        <button type="button" @click="cancelImport">取消</button>
        <button class="pool-save" type="button" :disabled="saving" @click="saveImport">
          {{ saving ? '保存中……' : '保存角色池' }}
        </button>
      </div>
    </section>

    <p v-if="notice" class="pool-notice">{{ notice }}</p>
    <p v-if="error" class="pool-notice error">{{ error }}</p>

    <section class="catalog-toolbar character-toolbar">
      <label class="catalog-search">
        <span>⌕</span>
        <input v-model="search" aria-label="搜索角色" placeholder="搜索角色名称" />
      </label>
      <select v-model="element" aria-label="筛选属性">
        <option v-for="item in elements" :key="item">{{ item }}</option>
      </select>
      <select v-model="path" aria-label="筛选命途">
        <option v-for="item in paths" :key="item">{{ item }}</option>
      </select>
      <select v-model="rarity" aria-label="筛选稀有度">
        <option>全部</option><option value="5">5 星</option><option value="4">4 星</option>
      </select>
      <select v-model="ownership" aria-label="筛选角色池">
        <option>全部角色</option><option>已拥有</option><option>喜欢</option>
      </select>
    </section>

    <p v-if="loading" class="catalog-state">黑塔正在整理角色档案……</p>
    <section v-else class="character-grid">
      <article
        v-for="character in filtered"
        :key="character.id"
        class="character-card"
        :class="{
          owned: selectedIds.has(character.id),
          selected: editMode && draftIds.has(character.id),
          'selection-mode': editMode,
        }"
        @click="toggleSelection(character.id)"
      >
        <button
          v-if="editMode"
          class="character-card-link character-select-button"
          type="button"
          :aria-label="`选择${character.name}`"
        >
          <div class="character-image">
            <img v-if="character.image_url" :src="character.image_url" :alt="character.name" loading="lazy" />
            <span v-else>{{ character.name.slice(0, 1) }}</span>
          </div>
          <div class="character-card-body">
            <div class="rarity-stars">{{ '★'.repeat(character.rarity) }}</div>
            <h2>{{ character.name }}</h2>
            <p><span>{{ character.element }}</span><i>·</i><span>{{ character.path }}</span></p>
          </div>
          <b class="card-arrow">{{ draftIds.has(character.id) ? '✓' : '+' }}</b>
        </button>
        <router-link
          v-else
          class="character-card-link"
          :to="`/characters/${character.id}`"
          :aria-label="`查看${character.name}详情`"
        >
          <div class="character-image">
            <img v-if="character.image_url" :src="character.image_url" :alt="character.name" loading="lazy" />
            <span v-else>{{ character.name.slice(0, 1) }}</span>
          </div>
          <div class="character-card-body">
            <div class="rarity-stars">{{ '★'.repeat(character.rarity) }}</div>
            <h2>{{ character.name }}</h2>
            <p><span>{{ character.element }}</span><i>·</i><span>{{ character.path }}</span></p>
          </div>
          <b class="card-arrow">↗</b>
        </router-link>
        <span v-if="selectedIds.has(character.id)" class="owned-badge">已拥有</span>
        <button
          v-if="!editMode && ownedIds.has(character.id)"
          class="favorite-button"
          :class="{ active: favoriteIds.has(character.id) }"
          type="button"
          :aria-label="favoriteIds.has(character.id) ? `取消喜欢${character.name}` : `标记喜欢${character.name}`"
          :title="favoriteIds.has(character.id) ? '取消喜欢' : '标记为喜欢'"
          @click.stop="toggleFavorite(character.id)"
        >{{ favoriteIds.has(character.id) ? '♥' : '♡' }}</button>
      </article>
    </section>
    <p v-if="!loading && !filtered.length" class="catalog-state">没有符合筛选条件的角色。</p>
  </AppShell>
</template>
