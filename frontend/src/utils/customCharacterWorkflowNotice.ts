export interface CustomCharacterWorkflowNotice {
  title: string
  description: string
  tone: 'info' | 'success' | 'warning'
}

/**
 * 将后端版本状态转换为玩家能理解的审核流程说明。
 * 管理员入口只保留在个人中心，避免把管理功能暴露在创作工作台。
 */
export function getCustomCharacterWorkflowNotice(
  status: string,
  reviewReason?: string,
): CustomCharacterWorkflowNotice | null {
  if (status === 'pending_review') {
    return {
      title: '等待管理员审核',
      description: '作品已经提交，当前版本不能继续改写；玩家自助审核报告仍保留在下方。管理员请从个人中心进入审核中心处理。',
      tone: 'info',
    }
  }

  if (status === 'published') {
    return {
      title: '审核通过，已公开',
      description: '这个版本已经进入社区角色库。后续修改会生成新的私有草稿，不会直接覆盖公开版本。',
      tone: 'success',
    }
  }

  if (status === 'rejected') {
    const reason = reviewReason?.trim() || '管理员尚未填写具体原因。'
    return {
      title: '管理员已打回修改',
      description: `打回原因：${reason} 请返回对应阶段修改，重新运行自助审核后再次提交。`,
      tone: 'warning',
    }
  }

  return null
}
