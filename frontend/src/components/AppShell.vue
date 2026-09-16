<script setup lang="ts">
import { computed, useSlots } from 'vue'
import { useRoute } from 'vue-router'

import railEmblem from '../assets/brand/rail-emblem.webp'
import { useAuthStore } from '../stores/auth'
import { useChatTaskStore } from '../stores/chatTasks'
import { useUiStore } from '../stores/ui'

defineProps<{ pageClass?: string }>()

const auth = useAuthStore()
const tasks = useChatTaskStore()
const ui = useUiStore()
const route = useRoute()
const slots = useSlots()
const hasInspector = computed(() => Boolean(slots.inspector))

const groups = [
  {
    name: '黑塔助手',
    modules: [
      {
        name: '与黑塔对话',
        desc: '由主 Agent 调度所有专业能力',
        to: '/',
        status: '在线',
        icon: 'M4 5h16v11H8l-4 4V5Zm4 4h8M8 12h5',
      },
    ],
  },
  {
    name: '游戏资料',
    modules: [
      {
        name: '游戏智库',
        desc: '角色、光锥、遗器与物品档案',
        to: '/characters',
        status: '4 类',
        icon: 'M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4Zm3 0v16M11 8h5M11 12h5',
      },
      {
        name: '活动与攻略',
        desc: '活动档案与 4.4 版本攻略',
        to: '/activities',
        status: '4.4',
        icon: 'M6 3v3M18 3v3M4 8h16M5 5h14v15H5V5Zm3 7h3v3H8v-3Z',
      },
      {
        name: '剧情档案',
        desc: '按版本、任务与场景阅读剧情',
        to: '/stories',
        status: '档案',
        icon: 'M4 4h7a3 3 0 0 1 3 3v13H7a3 3 0 0 0-3 1V4Zm16 0h-3a3 3 0 0 0-3 3v13h3a3 3 0 0 1 3 1V4Z',
      },
    ],
  },
  {
    name: '智能规划',
    modules: [
      {
        name: '智能配队',
        desc: '按角色池、定位与机制生成队伍',
        to: '/teams',
        status: 'Agent',
        icon: 'M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm8 1a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM3 20a5 5 0 0 1 10 0M13 20a4 4 0 0 1 8 0',
      },
      {
        name: '养成规划',
        desc: '多角色目标与材料合并',
        to: '/planning',
        status: 'Agent',
        icon: 'M4 19h16M6 17V9m6 8V4m6 13v-5M4 9l8-5 8 8',
      },
      {
        name: '每周规划',
        desc: '按体力预算安排本周刷取',
        to: '/weekly-plan',
        status: 'Agent',
        icon: 'M5 4h14v16H5V4Zm0 5h14M9 2v4M15 2v4m-7 7 2 2 5-5',
      },
    ],
  },
  {
    name: '创作与社区',
    modules: [
      {
        name: '角色创作工坊',
        desc: '黑塔多轮引导原创角色',
        to: '/creator',
        status: '创作',
        icon: 'm4 20 4-1 10-10-3-3L5 16l-1 4ZM13 8l3 3M4 4h6M4 8h3',
      },
      {
        name: '社区角色库',
        desc: '经过审核的玩家创作档案',
        to: '/community/characters',
        status: '社区',
        icon: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-4-7 2 2 5-6m-8 8h10',
      },
    ],
  },
  {
    name: '用户与管理',
    modules: [
      {
        name: '长期记忆',
        desc: '管理已确认的稳定偏好',
        to: '/profile/memories',
        status: '可控',
        icon: 'M12 3a6 6 0 0 0-6 6v6a4 4 0 0 0 4 4h4a4 4 0 0 0 4-4V9a6 6 0 0 0-6-6Zm-3 8h6m-6 4h4',
      },
    ],
  },
]

const themeLabel = computed(() => {
  const labels = { system: '跟随系统', dark: '深色主题', light: '浅色主题' }
  return labels[ui.theme]
})

function isActive(path: string) {
  return path === '/' ? route.path === '/' : route.path.startsWith(path)
}
</script>

<template>
  <main
    class="shell"
    :class="{
      'shell--expanded': ui.sidebarExpanded,
      'shell--inspector': hasInspector && ui.inspectorOpen,
    }"
  >
    <div
      v-if="ui.mobileNavigationOpen"
      class="shell-backdrop"
      aria-hidden="true"
      @click="ui.closeMobileNavigation"
    />

    <aside
      class="sidebar"
      :class="{ 'sidebar--mobile-open': ui.mobileNavigationOpen }"
      aria-label="主要功能"
    >
      <div class="sidebar-brand-row">
        <router-link class="brand" to="/" @click="ui.handleNavigation()">
          <img
            class="brand-emblem"
            :src="railEmblem"
            alt=""
          />
          <div class="brand-copy">
            <strong>星穹列车智库</strong>
            <small>STAR RAIL AGENTS</small>
          </div>
        </router-link>
        <button
          type="button"
          class="rail-button sidebar-collapse"
          :aria-label="ui.sidebarExpanded ? '收起侧边栏' : '展开侧边栏'"
          :aria-expanded="ui.sidebarExpanded"
          @click.stop="ui.toggleSidebar()"
        >
          <span aria-hidden="true">{{ ui.sidebarExpanded ? '‹' : '›' }}</span>
        </button>
      </div>

      <nav class="sidebar-navigation" data-tour="sidebar-nav">
        <section v-for="group in groups" :key="group.name" class="nav-group">
          <p class="nav-label">{{ group.name }}</p>
          <router-link
            v-for="module in group.modules"
            :key="module.to"
            :to="module.to"
            class="module"
            :class="{ active: isActive(module.to) }"
            :title="ui.sidebarExpanded ? undefined : module.name"
            @click="ui.handleNavigation()"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path :d="module.icon" />
            </svg>
            <span class="module-copy">
              <span class="module-title">
                <span>{{ module.name }}</span><em>{{ module.status }}</em>
              </span>
              <small>{{ module.desc }}</small>
            </span>
          </router-link>
        </section>
      </nav>

      <div class="sidebar-footer">
        <div class="sidebar-status" title="本地知识资源已连接">
          <i aria-hidden="true" />
          <span>本地知识资源已连接</span>
        </div>
        <router-link
          v-if="auth.user"
          class="account-entry"
          to="/profile"
          :title="auth.user.display_name"
        >
          <span>{{ auth.user.display_name.slice(0, 1).toUpperCase() }}</span>
          <div><strong>{{ auth.user.display_name }}</strong><small>@{{ auth.user.username }}</small></div>
        </router-link>
        <router-link v-else class="account-entry" to="/login" title="登录智库">
          <span>+</span>
          <div><strong>登录智库</strong><small>启用长期记忆</small></div>
        </router-link>
      </div>
    </aside>

    <section class="workspace-frame">
      <header class="app-toolbar">
        <button
          type="button"
          class="rail-button mobile-menu-button"
          aria-label="打开功能导航"
          @click="ui.mobileNavigationOpen = true"
        >
          <span aria-hidden="true">☰</span>
        </button>
        <div class="toolbar-brand">
          <img :src="railEmblem" alt="" />
          <span>STAR RAIL AGENTS</span>
        </div>
        <div class="toolbar-actions">
          <button
            type="button"
            class="rail-button theme-button"
            :aria-label="`切换主题，当前为${themeLabel}`"
            :title="themeLabel"
            @click="ui.cycleTheme"
          >
            <span aria-hidden="true">{{ ui.resolvedTheme === 'dark' ? '☾' : '☼' }}</span>
          </button>
          <button
            v-if="hasInspector"
            type="button"
            class="inspector-toggle"
            data-tour="inspector-toggle"
            :class="{ active: ui.inspectorOpen }"
            :aria-expanded="ui.inspectorOpen"
            aria-controls="agent-inspector"
            @click.stop="ui.toggleInspector()"
          >
            <span class="inspector-pulse" :class="{ live: tasks.activeJobs.length }" />
            Agent 过程
            <b v-if="tasks.activeJobs.length">{{ tasks.activeJobs.length }}</b>
          </button>
        </div>
      </header>
      <div class="workspace" :class="pageClass">
        <slot />
      </div>
    </section>

    <aside
      v-if="hasInspector"
      v-show="ui.inspectorOpen"
      id="agent-inspector"
      class="agent-inspector"
      :aria-hidden="!ui.inspectorOpen"
    >
      <slot name="inspector" />
    </aside>
  </main>
</template>
