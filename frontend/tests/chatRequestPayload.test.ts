import assert from 'node:assert/strict'
import test from 'node:test'

import { buildChatRequestPayload } from '../src/utils/chatRequestPayload.ts'


test('已有登录会话不重复上传前端历史，由后端按会话 ID 读取', () => {
  const payload = buildChatRequestPayload(
    '继续说明',
    '66951f1b-3f2e-47e0-ad97-b2a4c6619450',
    [{ role: 'assistant', content: 'a'.repeat(1103) }],
  )

  assert.equal(payload.conversation_id, '66951f1b-3f2e-47e0-ad97-b2a4c6619450')
  assert.deepEqual(payload.history, [])
})

test('临时会话历史满足后端的条数和单条长度限制', () => {
  const history = [
    { role: 'assistant' as const, content: '   ' },
    ...Array.from({ length: 14 }, (_, index) => ({
      role: index % 2 ? 'assistant' as const : 'user' as const,
      content: String(index).repeat(1200),
    })),
  ]

  const payload = buildChatRequestPayload('新问题', '', history)

  assert.equal(payload.conversation_id, null)
  assert.equal(payload.history.length, 12)
  assert.ok(payload.history.every((item) => item.content.length <= 1000))
  assert.ok(payload.history.every((item) => item.content.trim().length > 0))
})
