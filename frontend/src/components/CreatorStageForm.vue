<script setup lang="ts">
import { computed, reactive, watch } from 'vue'

import type { CustomCharacterPayload } from '../types/customCharacter'

const props = defineProps<{
  stage: number
  draft: CustomCharacterPayload
  disabled?: boolean
  submitLabel?: string
}>()
const emit = defineEmits<{ submit: [message: string, fields: Record<string, unknown>] }>()
const elements = ['物理', '火', '冰', '雷', '风', '量子', '虚数']
const paths = ['毁灭', '巡猎', '智识', '同谐', '虚无', '存护', '丰饶', '记忆', '欢愉']
const roleOptions = ['主C', '副C', '辅助', '生存']
const statLabels: Record<string, string> = { hp: '生命', attack: '攻击', defence: '防御', speed: '速度', taunt: '嘲讽', energy: '能量' }
const skillLabels: Record<string, string> = { basic: '普攻', skill: '战技', ultimate: '终结技', talent: '天赋', technique: '秘技' }
const form = reactive({
  name: '', rarity: 5, element: '量子', path: '虚无', summary: '',
  roles: [] as string[], core_mechanics: '', mechanic_tags: '',
  hp: 1000, attack: 500, defence: 450, speed: 100, taunt: 100, energy: 120,
  basic: '', skill: '', ultimate: '', talent: '', technique: '',
  elation_skill: '', memosprite_skill: '', memosprite_talent: '', story: '',
  eidolons: ['', '', '', '', '', ''] as string[],
})
const stageExample = computed(() => {
  const examples = {
    1: '示例：星澜，5 星，量子，虚无。通过记录敌人的“观测值”为量子队提供减抗。',
    2: '示例：定位选“辅助”；核心机制写清触发条件、持续时间和服务对象；标签可填“减抗、量子增益、追加攻击”。',
    3: '示例技能描述：战技——对指定敌人施加 2 回合观测标记，使其量子抗性降低；不要只写“造成大量伤害”。',
    4: '示例故事：她为什么登上列车、能力从何而来。记忆/欢愉命途还要补对应专属技能。',
  }
  return examples[props.stage as keyof typeof examples]
})

function hydrate() {
  const draft = props.draft
  form.name = draft.name ?? form.name
  form.rarity = draft.rarity ?? form.rarity
  form.element = draft.element ?? form.element
  form.path = draft.path ?? form.path
  form.summary = draft.summary ?? form.summary
  form.roles = [...(draft.roles ?? [])]
  form.core_mechanics = draft.core_mechanics ?? form.core_mechanics
  form.mechanic_tags = (draft.mechanic_tags ?? []).join('、')
  if (draft.base_stats) Object.assign(form, draft.base_stats)
  Object.assign(form, draft.skills ?? {}, draft.special_skills ?? {})
  form.story = draft.story ?? form.story
  form.eidolons = Array.from({ length: 6 }, (_, index) => draft.eidolons?.[index] ?? '')
}
watch(() => props.draft, hydrate, { immediate: true, deep: true })

function applyExample() {
  if (props.stage === 1) {
    Object.assign(form, {
      name: '星澜',
      rarity: 5,
      element: '量子',
      path: '虚无',
      summary: '记录敌人的观测值，为量子队降低抗性并创造输出窗口。',
    })
  } else if (props.stage === 2) {
    form.roles = ['辅助']
    form.core_mechanics = '战技施加持续 2 回合的观测标记，降低目标量子抗性；终结技延长标记并提高全队量子伤害。'
    form.mechanic_tags = '减抗、量子增益、标记'
  } else if (props.stage === 3) {
    Object.assign(form, { hp: 1080, attack: 520, defence: 470, speed: 105, taunt: 100, energy: 120 })
    form.basic = '对指定敌方单体造成量子属性伤害。'
    form.skill = '对指定敌人施加持续 2 回合的观测标记，使其量子抗性降低。'
    form.ultimate = '延长所有观测标记 1 回合，并使我方全体量子伤害提高 2 回合。'
    form.talent = '带有观测标记的敌人受到攻击后，星澜获得 1 层演算。'
    form.technique = '进入战斗时随机为一名敌人施加观测标记。'
  } else {
    form.story = '她曾负责记录一颗濒临崩解的星球，最终把无法解释的观测结果带上列车继续研究。'
    if (form.path === '欢愉') form.elation_skill = '消耗演算层数，对带有标记的敌人发动一次欢愉技。'
    if (form.path === '记忆') {
      form.memosprite_skill = '忆灵对带有观测标记的敌人发动协同攻击。'
      form.memosprite_talent = '忆灵存在期间，量子属性队友攻击标记目标后获得增益。'
    }
  }
}

function submit() {
  let fields: Record<string, unknown>
  if (props.stage === 1) {
    fields = { name: form.name, rarity: form.rarity, element: form.element, path: form.path, summary: form.summary }
  } else if (props.stage === 2) {
    fields = {
      roles: form.roles,
      core_mechanics: form.core_mechanics,
      mechanic_tags: form.mechanic_tags.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
    }
  } else if (props.stage === 3) {
    fields = {
      base_stats: { hp: form.hp, attack: form.attack, defence: form.defence, speed: form.speed, taunt: form.taunt, energy: form.energy },
      skills: { basic: form.basic, skill: form.skill, ultimate: form.ultimate, talent: form.talent, technique: form.technique },
    }
  } else {
    const special_skills: Record<string, string> = {}
    if (form.path === '欢愉') special_skills.elation_skill = form.elation_skill
    if (form.path === '记忆') {
      special_skills.memosprite_skill = form.memosprite_skill
      special_skills.memosprite_talent = form.memosprite_talent
    }
    fields = {
      special_skills,
      story: form.story,
      eidolons: form.eidolons.map((item) => item.trim()).filter(Boolean),
    }
  }
  emit('submit', `确认第 ${props.stage} 阶段输入。`, fields)
}
</script>

<template>
  <form class="creator-form" @submit.prevent="submit">
    <aside class="creator-helper wide">
      <div><strong>第 {{ stage }} 阶段怎么写？</strong><p>{{ stageExample }}</p></div>
      <button type="button" :disabled="disabled" @click="applyExample">填入可修改示例</button>
      <small>示例是玩家创作格式，不属于官方角色资料；填入后请按你的设定修改。</small>
    </aside>
    <template v-if="stage === 1">
      <label>角色名称<input id="creator-name" v-model.trim="form.name" required maxlength="48" /></label>
      <label>稀有度<select id="creator-rarity" v-model.number="form.rarity"><option :value="4">4 星</option><option :value="5">5 星</option></select></label>
      <label>属性<select id="creator-element" v-model="form.element"><option v-for="value in elements" :key="value">{{ value }}</option></select></label>
      <label>命途<select id="creator-path" v-model="form.path"><option v-for="value in paths" :key="value">{{ value }}</option></select></label>
      <label class="wide">一句简介<textarea id="creator-summary" v-model.trim="form.summary" required maxlength="500" rows="3" /></label>
    </template>
    <template v-else-if="stage === 2">
      <fieldset class="wide"><legend>战斗定位</legend><label v-for="role in roleOptions" :key="role" class="check"><input v-model="form.roles" type="checkbox" :value="role" />{{ role }}</label></fieldset>
      <label class="wide">核心机制<textarea id="creator-core_mechanics" v-model.trim="form.core_mechanics" required rows="5" /></label>
      <label class="wide">机制标签（顿号分隔）<input id="creator-mechanic_tags" v-model.trim="form.mechanic_tags" placeholder="减抗、追加攻击、召唤" /></label>
    </template>
    <template v-else-if="stage === 3">
      <label v-for="key in ['hp','attack','defence','speed','taunt','energy']" :key="key">{{ statLabels[key] }}<input :id="`creator-base_stats-${key}`" v-model.number="form[key as keyof typeof form]" type="number" min="1" required /></label>
      <label v-for="key in ['basic','skill','ultimate','talent','technique']" :key="key" class="wide">{{ skillLabels[key] }}<textarea :id="`creator-skills-${key}`" v-model.trim="form[key as keyof typeof form]" required rows="3" /></label>
    </template>
    <template v-else>
      <label v-if="form.path === '欢愉'" class="wide">欢愉技<textarea id="creator-special_skills-elation_skill" v-model.trim="form.elation_skill" required rows="4" /></label>
      <template v-if="form.path === '记忆'"><label class="wide">忆灵技<textarea id="creator-special_skills-memosprite_skill" v-model.trim="form.memosprite_skill" required rows="4" /></label><label class="wide">忆灵天赋<textarea id="creator-special_skills-memosprite_talent" v-model.trim="form.memosprite_talent" required rows="4" /></label></template>
      <label class="wide">角色故事（可选）<textarea id="creator-story" v-model.trim="form.story" rows="8" /></label>
      <fieldset class="wide eidolons"><legend>星魂（可选，最多 6 项）</legend><label v-for="index in 6" :key="index">星魂 {{ index }}<textarea :id="`creator-eidolons-${index - 1}`" v-model.trim="form.eidolons[index - 1]" rows="2" :placeholder="`第 ${index} 星魂效果`" /></label></fieldset>
    </template>
    <button class="wide" type="submit" :disabled="disabled">{{ submitLabel ?? '把本阶段交给黑塔检查' }}</button>
  </form>
</template>

<style scoped>
.creator-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; align-items: stretch; padding: 1rem; border: 1px solid var(--line); background: var(--panel); }
label { display: grid; gap: .4rem; color: var(--text-secondary); font-size: .8rem; }
.wide { grid-column: 1 / -1; }
input, select, textarea { width: 100%; border: 1px solid var(--line); padding: .7rem; color: var(--text); background: var(--surface-raised); font: inherit; }
textarea { resize: vertical; }
fieldset { border: 1px solid var(--line); color: var(--text-secondary); }
.eidolons { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; }
.eidolons legend { padding: 0 .35rem; }
.check { display: inline-flex; grid-auto-flow: column; align-items: center; margin-right: 1rem; }
.check input { width: auto; }
button { border: 1px solid var(--line-strong); padding: .8rem; color: var(--text); background: color-mix(in srgb, var(--gold) 12%, var(--surface)); cursor: pointer; }
.creator-helper { display: grid; grid-template-columns: 1fr auto; gap: .5rem 1rem; align-items: center; padding: .85rem; border: 1px solid var(--line-strong); background: color-mix(in srgb, var(--gold) 8%, var(--surface-raised)); }
.creator-helper strong { color: var(--text); }
.creator-helper p { margin: .3rem 0 0; color: var(--text-secondary) !important; line-height: 1.65; }
.creator-helper button { width: auto; }
.creator-helper small { grid-column: 1 / -1; color: var(--muted) !important; }
@media (max-width: 620px) { .creator-form, .eidolons { grid-template-columns: 1fr; } .wide { grid-column: auto; } }
</style>
