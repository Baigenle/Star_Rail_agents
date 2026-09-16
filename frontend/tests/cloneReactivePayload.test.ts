import assert from 'node:assert/strict'
import test from 'node:test'

import { reactive } from 'vue'

import { cloneReactivePayload } from '../src/utils/cloneReactivePayload.ts'


test('克隆 Vue 响应式角色草稿后可以安全修改并提交', () => {
  const payload = reactive({
    roles: ['辅助'],
    skills: { basic: '造成火属性伤害。' },
  })

  const cloned = cloneReactivePayload(payload)
  cloned.roles = ['主C']
  cloned.skills.basic = '对指定敌方单体造成火属性伤害。'

  assert.deepEqual(cloned.roles, ['主C'])
  assert.equal(cloned.skills.basic, '对指定敌方单体造成火属性伤害。')
  assert.deepEqual(payload.roles, ['辅助'])
  assert.equal(payload.skills.basic, '造成火属性伤害。')
})
