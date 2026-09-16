const typeLabels: Record<string, string> = {
  AvatarRank: '角色晋阶材料',
  TracePath: '行迹材料',
  CommonMonsterDrop: '普通敌人材料',
  WeeklyMonsterDrop: '历战余响材料',
  Material: '养成材料',
  Mission: '任务物品',
}

const rarityLabels: Record<string, string> = {
  Normal: '一星',
  NotNormal: '二星',
  Rare: '三星',
  VeryRare: '四星',
  SuperRare: '五星',
}

export const itemTypeLabel = (value: string) => typeLabels[value] ?? value
export const rarityLabel = (value: string) => rarityLabels[value] ?? value
