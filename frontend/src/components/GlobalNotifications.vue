<script setup lang="ts">
import { useRouter } from 'vue-router'

import { useChatTaskStore } from '../stores/chatTasks'

const tasks = useChatTaskStore()
const router = useRouter()

function openAnswer(conversationId?: string) {
  if (!conversationId) return
  void router.push({ path: '/', query: { conversation: conversationId } })
}
</script>

<template>
  <aside class="global-notifications" aria-live="polite" aria-label="问答完成通知">
    <article
      v-for="item in tasks.notifications.slice(0, 3)"
      :key="item.id"
      :class="item.kind"
    >
      <div>
        <strong>{{ item.title }}</strong>
        <p>{{ item.message }}</p>
      </div>
      <button
        v-if="item.conversationId"
        type="button"
        @click="openAnswer(item.conversationId)"
      >
        查看回答
      </button>
      <button
        type="button"
        class="dismiss"
        aria-label="关闭通知"
        @click="tasks.dismissNotification(item.id)"
      >
        ×
      </button>
    </article>
  </aside>
</template>

<style scoped>
.global-notifications { position: fixed; z-index: 100; left: 22px; bottom: 22px; display: grid; width: min(380px, calc(100vw - 44px)); gap: 10px; pointer-events: none; }
article { position: relative; display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: center; padding: 15px 42px 15px 16px; border: 1px solid rgba(168, 133, 255, .46); border-radius: 14px; background: rgba(12, 10, 28, .96); box-shadow: 0 18px 55px rgba(0, 0, 0, .38); pointer-events: auto; }
article.error { border-color: rgba(229, 111, 127, .55); }
strong { color: #eee8ff; font-size: 13px; }
p { overflow: hidden; margin: 4px 0 0; color: #928ba8; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
button { border: 1px solid rgba(185, 148, 255, .5); border-radius: 999px; padding: 7px 11px; color: #e8ddff; background: rgba(128, 82, 216, .18); cursor: pointer; }
.dismiss { position: absolute; top: 5px; right: 6px; border: 0; padding: 5px 8px; color: #88819b; background: transparent; }
</style>
