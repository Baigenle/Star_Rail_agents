<script setup lang="ts">
import { onMounted } from 'vue'

import GlobalNotifications from './components/GlobalNotifications.vue'
import { useAuthStore } from './stores/auth'
import { useChatTaskStore } from './stores/chatTasks'
import { useUiStore } from './stores/ui'

const auth = useAuthStore()
const tasks = useChatTaskStore()
const ui = useUiStore()

onMounted(async () => {
  ui.initialize()
  await auth.refresh()
  try {
    await tasks.initialize(auth.isAuthenticated)
  } catch {
    // 全局通知不可用时不阻断其他页面。
  }
})
</script>

<template>
  <router-view />
  <GlobalNotifications />
</template>
