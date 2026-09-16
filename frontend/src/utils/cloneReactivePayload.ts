import { toRaw } from 'vue'


/**
 * Vue 会把接口对象包装成 Proxy，而 structuredClone 不能直接克隆 Proxy。
 * 先取得原始 JSON 对象，再进行深拷贝，保证编辑表单不会修改当前页面快照。
 */
export function cloneReactivePayload<T>(payload: T): T {
  return structuredClone(toRaw(payload))
}
