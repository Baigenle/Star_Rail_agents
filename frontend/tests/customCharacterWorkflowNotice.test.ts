import assert from 'node:assert/strict'
import test from 'node:test'

import { getCustomCharacterWorkflowNotice } from '../src/utils/customCharacterWorkflowNotice.ts'


test('待审核作品明确说明自助审核报告仍然保留', () => {
  const notice = getCustomCharacterWorkflowNotice('pending_review')

  assert.equal(notice?.title, '等待管理员审核')
  assert.match(notice?.description ?? '', /自助审核报告仍保留/)
  assert.match(notice?.description ?? '', /个人中心/)
})

test('已发布和被驳回作品显示各自的后续动作', () => {
  assert.equal(getCustomCharacterWorkflowNotice('published')?.title, '审核通过，已公开')
  assert.match(
    getCustomCharacterWorkflowNotice('rejected', '技能描述需要补充触发条件')?.description ?? '',
    /技能描述需要补充触发条件/,
  )
  assert.equal(getCustomCharacterWorkflowNotice('draft'), null)
})
