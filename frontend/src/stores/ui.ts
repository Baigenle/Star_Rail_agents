import { defineStore } from 'pinia'

export type ThemePreference = 'system' | 'dark' | 'light'

const THEME_KEY = 'star_rail_theme'
const SIDEBAR_KEY = 'star_rail_sidebar_expanded'

export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: (localStorage.getItem(THEME_KEY) as ThemePreference | null) ?? 'system',
    sidebarExpanded: localStorage.getItem(SIDEBAR_KEY) === 'true',
    mobileNavigationOpen: false,
    inspectorOpen: false,
    initialized: false,
  }),
  getters: {
    resolvedTheme: (state): 'dark' | 'light' => {
      if (state.theme !== 'system') return state.theme
      return window.matchMedia('(prefers-color-scheme: light)').matches
        ? 'light'
        : 'dark'
    },
  },
  actions: {
    initialize() {
      if (this.initialized) return
      this.initialized = true
      this.applyTheme()
      window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
        if (this.theme === 'system') this.applyTheme()
      })
    },
    applyTheme() {
      document.documentElement.dataset.theme = this.resolvedTheme
      document.documentElement.style.colorScheme = this.resolvedTheme
    },
    cycleTheme() {
      const sequence: ThemePreference[] = ['system', 'dark', 'light']
      this.theme = sequence[(sequence.indexOf(this.theme) + 1) % sequence.length]
      localStorage.setItem(THEME_KEY, this.theme)
      this.applyTheme()
    },
    toggleSidebar() {
      this.sidebarExpanded = !this.sidebarExpanded
      localStorage.setItem(SIDEBAR_KEY, String(this.sidebarExpanded))
    },
    handleNavigation() {
      // 桌面侧栏的展开状态必须跨路由保留；只有移动端抽屉需要在跳转后关闭。
      if (window.matchMedia('(max-width: 820px)').matches) {
        this.mobileNavigationOpen = false
      }
    },
    toggleInspector() {
      this.inspectorOpen = !this.inspectorOpen
    },
    closeInspector() {
      this.inspectorOpen = false
    },
    closeMobileNavigation() {
      this.mobileNavigationOpen = false
    },
  },
})
