export interface ChatHistoryInput {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatRequestPayload {
  message: string
  conversation_id: string | null
  history: ChatHistoryInput[]
}

const MAX_HISTORY_ITEMS = 12
const MAX_HISTORY_CONTENT_LENGTH = 1000

/**
 * 统一聊天请求载荷。
 * 已登录的既有会话由后端按 conversation_id 读取历史，避免重复上传长回答；
 * 临时会话则按后端契约裁剪历史，防止在进入 Agent 前被 422 拒绝。
 */
export function buildChatRequestPayload(
  message: string,
  conversationId: string | undefined,
  history: ChatHistoryInput[],
): ChatRequestPayload {
  const normalizedConversationId = conversationId?.trim() || null
  const normalizedHistory = normalizedConversationId
    ? []
    : history
        .filter((item) => item.content.trim().length > 0)
        .slice(-MAX_HISTORY_ITEMS)
        .map((item) => ({
          role: item.role,
          content: item.content.slice(0, MAX_HISTORY_CONTENT_LENGTH),
        }))

  return {
    message,
    conversation_id: normalizedConversationId,
    history: normalizedHistory,
  }
}
