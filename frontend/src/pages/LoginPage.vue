<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const account = ref('')
const username = ref('')
const email = ref('')
const displayName = ref('')
const password = ref('')
const error = ref('')

async function submit() {
  error.value = ''
  try {
    if (mode.value === 'login') await auth.login(account.value.trim(), password.value)
    else await auth.register(username.value.trim(), email.value.trim(), password.value, displayName.value.trim())
    // 新注册的用户直接落到聊天主页，由新手引导带一圈功能。
    await router.push(mode.value === 'register' ? '/' : String(route.query.redirect || '/profile'))
  } catch (reason) { error.value = auth.errorMessage(reason) }
}
</script>

<template>
  <AppShell>
    <section class="auth-layout">
      <div class="auth-intro"><span class="eyebrow">HERTA IDENTITY SYSTEM</span><h1>让本天才记住你</h1><p>登录后可以建立角色库、保存常用队伍，并让黑塔在后续回答中读取你的长期偏好。</p><div class="auth-points"><span>角色收藏</span><span>长期记忆</span><span>个性化推荐</span></div></div>
      <form class="auth-card" @submit.prevent="submit">
        <div class="auth-switch"><button type="button" :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button><button type="button" :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button></div>
        <template v-if="mode === 'login'">
          <label><span>用户名或邮箱</span><input v-model="account" required autocomplete="username" placeholder="输入用户名或邮箱" /></label>
        </template>
        <template v-else>
          <label><span>用户名</span><input v-model="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+" autocomplete="username" placeholder="字母、数字或下划线" /></label>
          <label><span>邮箱</span><input v-model="email" required type="email" autocomplete="email" placeholder="name@example.com" /></label>
          <label><span>显示名称</span><input v-model="displayName" required maxlength="48" autocomplete="nickname" placeholder="黑塔如何称呼你" /></label>
        </template>
        <label><span>密码</span><input v-model="password" required type="password" minlength="8" maxlength="128" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" placeholder="至少 8 位" /></label>
        <p v-if="error" class="error">{{ error }}</p>
        <button class="auth-submit" type="submit" :disabled="auth.loading">{{ auth.loading ? '处理中……' : mode === 'login' ? '登录智库' : '创建身份' }}</button>
        <small>密码使用 scrypt 加盐哈希保存，服务器不会保存明文密码。</small>
      </form>
    </section>
  </AppShell>
</template>
