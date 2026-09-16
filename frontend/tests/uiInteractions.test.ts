import assert from 'node:assert/strict'
import test from 'node:test'

import { createPinia, setActivePinia } from 'pinia'

import { useUiStore } from '../src/stores/ui.ts'


function installBrowserStubs() {
  const values = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    },
  })
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      matchMedia: () => ({ matches: false }),
    },
  })
  return values
}

test('展开状态会保存，桌面端路由切换不会收起侧边栏', () => {
  const values = installBrowserStubs()
  setActivePinia(createPinia())
  const ui = useUiStore()

  ui.toggleSidebar()
  ui.handleNavigation()

  assert.equal(ui.sidebarExpanded, true)
  assert.equal(values.get('star_rail_sidebar_expanded'), 'true')
})

test('执行过程面板可以通过显式动作打开和关闭', () => {
  installBrowserStubs()
  setActivePinia(createPinia())
  const ui = useUiStore()

  ui.toggleInspector()
  assert.equal(ui.inspectorOpen, true)
  ui.closeInspector()
  assert.equal(ui.inspectorOpen, false)
})
