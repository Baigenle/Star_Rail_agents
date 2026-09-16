<script setup lang="ts">
import { computed } from 'vue'

import type { SelfReviewIssue, SelfReviewReport, SelfReviewSeverity } from '../types/customCharacter'

const props = defineProps<{ report: SelfReviewReport }>()
const emit = defineEmits<{ edit: [field: string] }>()

const severityGroups: Array<{ key: SelfReviewSeverity; title: string }> = [
  { key: 'error', title: '必须修复' },
  { key: 'warning', title: '建议修复' },
  { key: 'suggestion', title: '可选优化' },
]
const fieldLabels: Record<string, string> = {
  name: '角色名称', summary: '角色简介', roles: '战斗定位', core_mechanics: '核心机制',
  mechanic_tags: '机制标签', base_stats: '基础属性', skills: '技能档案', story: '角色故事',
  'skills.basic': '普攻', 'skills.skill': '战技', 'skills.ultimate': '终结技',
  'skills.talent': '天赋', 'skills.technique': '秘技',
  'special_skills.elation_skill': '欢愉技', 'special_skills.memosprite_skill': '忆灵技',
  'special_skills.memosprite_talent': '忆灵天赋',
}

const groupedIssues = computed(() => {
  const all = props.report.categories.flatMap((category) => category.issues)
  return severityGroups.map((group) => ({
    ...group,
    issues: all.filter((issue) => issue.severity === group.key),
  })).filter((group) => group.issues.length)
})

function fieldLabel(issue: SelfReviewIssue): string {
  if (issue.field.startsWith('eidolons.')) return `星魂 ${Number(issue.field.split('.')[1]) + 1}`
  return fieldLabels[issue.field] ?? issue.field
}
</script>

<template>
  <section class="review-panel" aria-labelledby="self-review-title">
    <header class="review-header">
      <div>
        <span class="eyebrow">PLAYER REVIEW AGENT</span>
        <h2 id="self-review-title">创作自助审核报告</h2>
        <p>{{ report.summary }}</p>
      </div>
      <div class="score-seal" :data-verdict="report.verdict" aria-label="审核总分">
        <strong>{{ report.overall_score }}</strong><span>/ 100</span>
      </div>
    </header>

    <div class="category-list" aria-label="审核维度得分">
      <article v-for="category in report.categories" :key="category.key">
        <div><b>{{ category.name }}</b><span>权重 {{ category.weight }}%</span></div>
        <progress :value="category.score" max="100">{{ category.score }}%</progress>
        <strong>{{ category.score }}</strong>
      </article>
    </div>

    <div v-if="groupedIssues.length" class="issue-groups">
      <section v-for="group in groupedIssues" :key="group.key" :class="['issue-group', group.key]">
        <h3>{{ group.title }} <span>{{ group.issues.length }}</span></h3>
        <article v-for="issue in group.issues" :key="`${issue.field}-${issue.code}`">
          <div>
            <b>{{ fieldLabel(issue) }}</b>
            <p>{{ issue.description }}</p>
            <small>完善建议：{{ issue.suggestion }}</small>
          </div>
          <button type="button" @click="emit('edit', issue.field)">返回修改</button>
        </article>
      </section>
    </div>
    <p v-else class="clean-state">未发现需要修改的问题，可以进入提交确认。</p>

    <section v-if="report.highlights.length" class="highlights">
      <h3>设计亮点</h3>
      <ul><li v-for="highlight in report.highlights" :key="highlight">{{ highlight }}</li></ul>
    </section>
    <footer>
      <span>{{ report.model_used ? '确定性规则 + 推理模型' : '确定性规则（模型不可用时降级）' }}</span>
      <time :datetime="report.generated_at">{{ new Date(report.generated_at).toLocaleString('zh-CN') }}</time>
    </footer>
  </section>
</template>

<style scoped>
.review-panel { display: grid; gap: 1rem; margin-top: 1rem; padding: 1.25rem; border: 1px solid var(--line-strong); background: var(--panel); }
.review-header { display: flex; justify-content: space-between; gap: 1.5rem; align-items: start; }
.review-header h2 { margin: .25rem 0; }
.review-header p { max-width: 42rem; margin: 0; color: var(--text-secondary); line-height: 1.65; }
.score-seal { display: grid; place-items: center; flex: 0 0 6rem; min-height: 6rem; border: 1px solid var(--gold); color: var(--gold); }
.score-seal strong { font: 700 2rem/1 Georgia, "Times New Roman", serif; }
.score-seal span { font-size: .72rem; }
.score-seal[data-verdict="rejected"] { border-color: var(--danger); color: var(--danger); }
.category-list { display: grid; gap: .65rem; padding: 1rem; border: 1px solid var(--line); background: var(--surface-raised); }
.category-list article { display: grid; grid-template-columns: minmax(8rem, .7fr) minmax(10rem, 1fr) 2.5rem; gap: .8rem; align-items: center; }
.category-list article div { display: flex; justify-content: space-between; gap: .5rem; }
.category-list span { color: var(--muted); font-size: .72rem; }
progress { width: 100%; height: .5rem; accent-color: var(--gold); }
.issue-groups { display: grid; gap: 1rem; }
.issue-group { display: grid; gap: .55rem; }
.issue-group h3 { margin: 0; font-size: 1rem; }
.issue-group h3 span { color: var(--muted); }
.issue-group article { display: flex; justify-content: space-between; gap: 1rem; padding: .85rem; border-left: 3px solid var(--line-strong); background: var(--surface-raised); }
.issue-group.error article { border-left-color: var(--danger); }
.issue-group.warning article { border-left-color: var(--gold); }
.issue-group p { margin: .3rem 0; color: var(--text-secondary); line-height: 1.55; }
.issue-group small { color: var(--muted); line-height: 1.5; }
.issue-group button { align-self: center; flex: 0 0 auto; border: 1px solid var(--line-strong); padding: .55rem .75rem; color: var(--text); background: transparent; cursor: pointer; }
.highlights { padding: 1rem; border: 1px solid var(--line); background: color-mix(in srgb, var(--gold) 7%, var(--surface-raised)); }
.highlights h3 { margin-top: 0; }
.highlights li { margin: .35rem 0; color: var(--text-secondary); }
.clean-state { padding: 1rem; color: var(--text-secondary); background: var(--surface-raised); }
footer { display: flex; justify-content: space-between; gap: 1rem; color: var(--muted); font-size: .72rem; }
@media (max-width: 680px) {
  .review-header { display: grid; }
  .score-seal { width: 100%; min-height: 4rem; }
  .category-list article { grid-template-columns: 1fr 2.5rem; }
  .category-list article div { grid-column: 1 / -1; }
  .issue-group article, footer { display: grid; }
  .issue-group button { width: 100%; }
}
</style>
