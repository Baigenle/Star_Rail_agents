<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { getCharacterPool, getSavedTeams } from '../services/api'
import { useAuthStore } from '../stores/auth'
import type { CharacterPool } from '../types/profile'

const auth = useAuthStore()
const router = useRouter()
const pool = ref<CharacterPool>({ items: [], total: 0, favorites: 0 })
const error = ref('')
const savedTeamCount = ref(0)

onMounted(async () => {
  await auth.refresh()
  if (!auth.isAuthenticated) {
    await router.replace('/login')
    return
  }
  try {
    const [characters, teams] = await Promise.all([getCharacterPool(), getSavedTeams()])
    pool.value = characters
    savedTeamCount.value = teams.length
  } catch (reason) {
    error.value = auth.errorMessage(reason)
  }
})

function logout() {
  auth.logout()
  router.push('/')
}
</script>

<template>
  <AppShell>
    <template v-if="auth.user">
      <header class="catalog-header">
        <div>
          <span class="eyebrow">TRAILBLAZER PROFILE</span>
          <h1>{{ auth.user.display_name }}</h1>
          <p>这是黑塔为你建立的个人智库档案。</p>
        </div>
        <button class="profile-logout" @click="logout">退出登录</button>
      </header>
      <p v-if="error" class="pool-notice error">{{ error }}</p>
      <section class="profile-grid">
        <article class="profile-card identity-card">
          <span class="profile-avatar">{{ auth.user.display_name.slice(0, 1).toUpperCase() }}</span>
          <div>
            <small>USER ID · {{ auth.user.id }}</small>
            <h2>@{{ auth.user.username }}</h2>
            <p>{{ auth.user.email }}</p>
            <em>加入于 {{ new Date(auth.user.created_at).toLocaleDateString() }}</em>
          </div>
        </article>
        <article class="profile-card">
          <small>我的角色</small>
          <strong>{{ pool.total }}</strong>
          <p>已保存到角色池，可用于配队和养成规划。</p>
        </article>
        <article class="profile-card">
          <small>喜欢角色</small>
          <strong>{{ pool.favorites }}</strong>
          <p>{{ pool.favorites ? pool.items.filter((item) => item.is_favorite).map((item) => item.name).slice(0, 3).join('、') : '还没有标记喜欢的角色。' }}</p>
        </article>
        <article class="profile-card">
          <small>常用队伍</small>
          <strong>{{ savedTeamCount }}</strong>
          <p>{{ savedTeamCount ? '已保存，可用于后续配队与个性化推荐。' : '还没有保存常用队伍。' }}</p>
        </article>
      </section>
      <section class="detail-section">
        <div class="section-heading">
          <span>01</span>
          <div>
            <h2>我的角色池</h2>
            <p>继续批量增删角色，或标记喜欢角色；已有数据会长期保存在账户中。</p>
          </div>
        </div>
        <router-link class="profile-action" to="/characters">管理我的角色池 ↗</router-link>
      </section>
      <section v-if="auth.user.is_admin" class="detail-section admin-center">
        <div class="section-heading">
          <span>ADMIN</span>
          <div>
            <h2>内容审核中心</h2>
            <p>审核入口只对管理员显示。驳回内容时必须填写原因，作者会在作品状态中看到审核结果。</p>
          </div>
        </div>
        <div class="admin-actions">
          <router-link class="profile-action" to="/admin/reviews">审核社区角色 ↗</router-link>
          <router-link class="profile-action" to="/admin/activity-guide-reviews">审核活动攻略 ↗</router-link>
        </div>
      </section>
    </template>
  </AppShell>
</template>

<style scoped>
.admin-actions { display: flex; flex-wrap: wrap; gap: .75rem; }
</style>
