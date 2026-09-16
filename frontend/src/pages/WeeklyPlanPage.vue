<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import AppShell from '../components/AppShell.vue'
import {
  generateWeeklyPlan,
  getCurrentWeeklyPlan,
  getDailyPlan,
  patchDailyTask,
  updateWeeklyTask,
} from '../services/api'
import type { DailyPlan, DailyTaskSlice, WeeklyPlan, WeeklyTask } from '../types/planning'

type ViewMode = 'week' | 'today'

const viewMode = ref<ViewMode>('week')

const stamina = ref(1680)
const weeklyRuns = ref(3)
const plan = ref<WeeklyPlan | null>(null)
const loading = ref(false)
const error = ref('')

const daily = ref<DailyPlan | null>(null)
const dailyLoading = ref(false)
const todayIso = ref('')
const selectedDate = ref('')

const WEEKDAY_NAMES = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
const RING_LEN = 2 * Math.PI * 52

const completed = computed(
  () => plan.value?.tasks.filter((task) => task.completed).length ?? 0,
)

const weekDates = computed(() => {
  if (!daily.value) return []
  return WEEKDAY_NAMES.map((_, index) => isoAddDays(daily.value!.week_start, index))
})

const requiredPct = computed(() => {
  const stats = plan.value?.statistics
  if (!stats || stats.required_scheduled <= 0) return 0
  return Math.min(
    Math.round((stats.required_completed / stats.required_scheduled) * 100),
    100,
  )
})

const relicPct = computed(() => {
  const stats = plan.value?.statistics
  if (!stats || stats.recommended_scheduled <= 0) return 0
  return Math.min(
    Math.round((stats.recommended_completed / stats.recommended_scheduled) * 100),
    100,
  )
})

function weekdayLabel(iso: string): string {
  const day = new Date(`${iso}T00:00:00`).getDay()
  return WEEKDAY_NAMES[day]
}

function planPct(entry: { scheduled_runs: number; completed_runs: number }): number {
  if (entry.scheduled_runs <= 0) return 0
  return Math.min(Math.round((entry.completed_runs / entry.scheduled_runs) * 100), 100)
}

const ringRatio = computed(() => {
  if (!daily.value || daily.value.stamina_cap <= 0) return 0
  return Math.min(daily.value.completed_stamina / daily.value.stamina_cap, 1)
})

const ringOffset = computed(() => RING_LEN * (1 - ringRatio.value))

const dateLabel = computed(() => {
  if (!daily.value) return ''
  const [, month, day] = daily.value.date.split('-')
  return `${Number(month)} 月 ${Number(day)} 日 · ${daily.value.weekday_label}`
})

function toISO(value: Date): string {
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${value.getFullYear()}-${month}-${day}`
}

function isoAddDays(iso: string, days: number): string {
  const value = new Date(`${iso}T00:00:00`)
  value.setDate(value.getDate() + days)
  return toISO(value)
}

async function generate() {
  loading.value = true
  error.value = ''
  try {
    plan.value = await generateWeeklyPlan(stamina.value, weeklyRuns.value)
    await refreshDaily(selectedDate.value || undefined)
  } catch {
    error.value = '每周计划生成失败。请先在养成规划中保存并启用至少一份方案。'
  } finally {
    loading.value = false
  }
}

async function toggle(task: WeeklyTask) {
  if (!plan.value) return
  plan.value = await updateWeeklyTask(plan.value.id, task.id, !task.completed)
}

async function refreshDaily(date?: string) {
  dailyLoading.value = true
  try {
    daily.value = await getDailyPlan(date || undefined)
  } catch {
    daily.value = null
  } finally {
    dailyLoading.value = false
  }
}

async function switchView(mode: ViewMode) {
  viewMode.value = mode
  if (mode === 'today' && !daily.value) await refreshDaily(selectedDate.value || undefined)
}

async function switchDay(iso: string) {
  selectedDate.value = iso
  await refreshDaily(iso)
}

async function toggleDaily(item: DailyTaskSlice) {
  daily.value = await patchDailyTask(
    selectedDate.value,
    item.weekly_task_id,
    !item.completed,
  )
  plan.value = await getCurrentWeeklyPlan()
}

onMounted(async () => {
  try {
    plan.value = await getCurrentWeeklyPlan()
    stamina.value = plan.value.stamina_budget
    weeklyRuns.value = plan.value.weekly_runs_remaining
  } catch {
    plan.value = null
  }
  try {
    daily.value = await getDailyPlan()
    todayIso.value = daily.value.date
    selectedDate.value = daily.value.date
  } catch {
    daily.value = null
  }
})
</script>

<template>
  <AppShell>
    <div class="plan-page">
      <header class="weekly-head">
        <div>
          <span class="eyebrow">WEEKLY PLANNING AGENT</span>
          <h1>每周养成规划</h1>
          <p>只读取已保存且启用的养成方案。历战余响优先，再按材料缺口安排其他副本。</p>
        </div>
        <div class="head-side">
          <div class="view-switch" role="tablist" aria-label="切换周计划或今日视图">
            <span class="switch-pill" :class="{ right: viewMode === 'today' }" aria-hidden="true"></span>
            <button
              type="button"
              role="tab"
              class="switch-option"
              :class="{ active: viewMode === 'week' }"
              :aria-selected="viewMode === 'week'"
              @click="switchView('week')"
            >本周</button>
            <button
              type="button"
              role="tab"
              class="switch-option"
              :class="{ active: viewMode === 'today' }"
              :aria-selected="viewMode === 'today'"
              @click="switchView('today')"
            >今日</button>
          </div>
          <router-link to="/planning">调整养成方案 →</router-link>
        </div>
      </header>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <Transition name="view" mode="out-in">
        <section v-if="viewMode === 'week'" key="week">
          <section class="weekly-controls">
            <label>
              <span>本周可用体力</span><strong>{{ stamina }}</strong>
              <input v-model.number="stamina" type="range" min="0" max="2400" step="10" />
            </label>
            <label>
              <span>历战余响剩余次数</span><strong>{{ weeklyRuns }}</strong>
              <input v-model.number="weeklyRuns" type="range" min="0" max="3" />
            </label>
            <button type="button" :disabled="loading" @click="generate">
              {{ loading ? '黑塔安排中…' : plan ? '重新生成本周计划' : '生成本周计划' }}
            </button>
            <small class="gen-hint">以今天为起点，重排未来 7 天</small>
          </section>

          <template v-if="plan">
            <section class="weekly-summary">
              <article><small>周期</small><strong>{{ plan.week_start }} → {{ plan.week_end }}</strong></article>
              <article><small>体力分配</small><strong>{{ plan.allocated_stamina }} / {{ plan.stamina_budget }}</strong></article>
              <article><small>任务进度</small><strong>{{ completed }} / {{ plan.tasks.length }}</strong></article>
            </section>

            <section v-if="plan.statistics" class="stats-panel">
              <header class="stats-head">
                <span class="eyebrow">PLAN PROGRESS</span>
                <h2>方案进度</h2>
                <span v-if="plan.statistics.plan_complete" class="complete-chip">方案已完成 ✓</span>
              </header>
              <div class="stats-grid">
                <article>
                  <small>养成刚需（不含隧洞）</small>
                  <strong>{{ plan.statistics.required_completed }} / {{ plan.statistics.required_scheduled }} 次</strong>
                  <div class="bar"><i :style="{ width: requiredPct + '%' }"></i></div>
                  <em>{{ requiredPct }}%</em>
                </article>
                <article>
                  <small>侵蚀隧洞 · 推荐刷取（不计入完成）</small>
                  <strong>{{ plan.statistics.recommended_completed }} / {{ plan.statistics.recommended_scheduled }} 次</strong>
                  <div class="bar"><i class="relic" :style="{ width: relicPct + '%' }"></i></div>
                  <em>{{ relicPct }}%</em>
                </article>
                <article
                  v-for="entry in plan.statistics.plans"
                  :key="entry.plan_id"
                >
                  <small>{{ entry.plan_name }}</small>
                  <strong>{{ entry.completed_runs }} / {{ entry.scheduled_runs }} 次</strong>
                  <div class="bar"><i :style="{ width: planPct(entry) + '%' }"></i></div>
                  <em>{{ planPct(entry) }}%</em>
                </article>
              </div>
            </section>

            <section class="task-list">
              <article
                v-for="task in plan.tasks"
                :key="task.id"
                :class="{ completed: task.completed, weekly: task.dungeon_type === '历战余响' }"
              >
                <button
                  type="button"
                  class="check"
                  :aria-label="task.completed ? '标为未完成' : '标为完成'"
                  @click="toggle(task)"
                >{{ task.completed ? '✓' : '' }}</button>
                <div>
                  <div class="task-title">
                    <strong>{{ task.title }}</strong>
                    <span>优先级 {{ task.priority }}</span>
                    <em v-if="task.stamina_cost">{{ task.stamina_cost }} 体力</em>
                    <span v-if="task.completed_runs" class="progress-chip">
                      已完成 {{ task.completed_runs }} / {{ task.run_count }} 次
                    </span>
                  </div>
                  <p>{{ task.detail }}</p>
                  <div class="target-list">
                    <component
                      :is="target.entity_url ? 'router-link' : 'span'"
                      v-for="target in task.targets"
                      :key="target.key"
                      :to="target.entity_url"
                    >
                      {{ target.name }}
                      <b v-if="target.required_quantity">×{{ target.required_quantity.toLocaleString() }}</b>
                    </component>
                  </div>
                </div>
              </article>
            </section>

            <aside class="plan-notice">
              <strong>计算口径</strong>
              <p>{{ plan.notice }}</p>
              <small>{{ plan.evidence_version }}</small>
            </aside>
          </template>
          <p v-else class="empty-hint">本周计划尚未生成。设置体力预算后点击「生成本周计划」。</p>
        </section>

        <section v-else key="today" class="daily-view">
          <nav class="day-picker" aria-label="选择本周日期">
            <button
              v-for="iso in weekDates"
              :key="iso"
              type="button"
              class="day-chip"
              :class="{ active: iso === selectedDate, today: iso === todayIso }"
              @click="switchDay(iso)"
            >
              {{ weekdayLabel(iso) }}
              <small v-if="iso === todayIso">今日</small>
            </button>
          </nav>

          <section class="daily-summary" :class="{ loading: dailyLoading }">
            <div class="ring-wrap" role="img" :aria-label="`今日已完成体力 ${daily?.completed_stamina ?? 0} / ${daily?.stamina_cap ?? 240}`">
              <svg viewBox="0 0 120 120" class="ring">
                <circle class="ring-track" cx="60" cy="60" r="52" />
                <circle
                  class="ring-value"
                  cx="60"
                  cy="60"
                  r="52"
                  :stroke-dasharray="RING_LEN"
                  :stroke-dashoffset="ringOffset"
                />
              </svg>
              <div class="ring-center">
                <strong>{{ daily?.completed_stamina ?? 0 }}</strong>
                <small>/ {{ daily?.stamina_cap ?? 240 }} 体力</small>
              </div>
            </div>
            <div class="daily-meta">
              <h2>{{ dateLabel }}</h2>
              <p v-if="daily">
                今日已安排 {{ daily.planned_stamina }} 点 · 已完成
                {{ daily.completed_stamina }} 点 · 本周计划
                {{ daily.weekly_allocated }} / {{ daily.weekly_budget }} 点
              </p>
              <p class="daily-notice">{{ daily?.notice ?? '本周计划尚未生成，先回到「本周」生成计划。' }}</p>
            </div>
          </section>

          <TransitionGroup v-if="daily && daily.items.length" name="slice" tag="section" class="daily-list" appear>
            <article
              v-for="(item, index) in daily.items"
              :key="item.weekly_task_id"
              class="daily-card"
              :class="{ boss: item.is_weekly_boss, done: item.completed }"
              :style="{ '--stagger': `${index * 55}ms` }"
            >
              <button
                type="button"
                class="check"
                :class="{ filled: item.completed }"
                :aria-label="item.completed ? '取消完成' : '标记完成'"
                @click="toggleDaily(item)"
              >{{ item.completed ? '✓' : '' }}</button>
              <div>
                <div class="task-title">
                  <strong>{{ item.title }}</strong>
                  <span v-if="item.is_weekly_boss" class="boss-badge">周本优先</span>
                  <span v-if="!item.is_required" class="rec-badge">推荐</span>
                  <em>今日 {{ item.runs_planned }} 次 · {{ item.stamina }} 体力</em>
                  <span>本周共 {{ item.run_count_week }} 次</span>
                  <span v-if="item.completed" class="done-chip">已完成</span>
                </div>
                <div class="target-list">
                  <component
                    :is="target.entity_url ? 'router-link' : 'span'"
                    v-for="target in item.targets"
                    :key="target.key"
                    :to="target.entity_url"
                  >
                    {{ target.name }}
                    <b v-if="target.required_quantity">×{{ target.required_quantity.toLocaleString() }}</b>
                  </component>
                </div>
              </div>
            </article>
          </TransitionGroup>
          <p v-else-if="!dailyLoading" class="empty-hint">
            {{ todayIso === selectedDate
              ? '本日没有排程任务。回到「本周」先生成或更新计划。'
              : '这一天没有排程任务。' }}
          </p>

          <aside v-if="daily" class="plan-notice">
            <strong>计算口径</strong>
            <p>{{ daily.notice }}</p>
            <small>{{ daily.evidence_version }}</small>
          </aside>
        </section>
      </Transition>
    </div>
  </AppShell>
</template>

<style scoped>
.plan-page {
  --boss-line: rgba(230, 201, 130, .55);
  --boss-tint: rgba(90, 67, 23, .16);
  --notice-tint: rgba(233, 200, 117, .08);
  --on-gold: #282219;
  --deferred-color: #d0a35e;
  --chip-active-tint: rgba(233, 200, 117, .12);
  --done-chip-bg: rgba(143, 198, 162, .18);
  --done-chip-text: #8fc6a2;
}
:global(html[data-theme="light"]) .plan-page {
  --boss-line: rgba(110, 78, 23, .45);
  --boss-tint: rgba(166, 124, 32, .10);
  --notice-tint: rgba(166, 124, 32, .08);
  --on-gold: #2f2413;
  --deferred-color: #8a5c14;
  --chip-active-tint: rgba(166, 124, 32, .14);
  --done-chip-bg: rgba(64, 122, 84, .14);
  --done-chip-text: #3d7250;
}

.weekly-head { display: flex; justify-content: space-between; gap: 24px; align-items: end; margin-bottom: 25px; }
.weekly-head h1 { margin: 5px 0; }
.weekly-head p { color: var(--muted); }
.head-side { display: grid; gap: 12px; justify-items: end; }
.head-side a { color: var(--accent-text); }

/* 本周 / 今日 滑动切换 */
.view-switch { position: relative; display: inline-grid; grid-auto-flow: column; padding: 4px; border: 1px solid var(--line-strong); border-radius: 999px; background: var(--surface-muted); }
.switch-pill { position: absolute; top: 4px; left: 4px; width: calc(50% - 4px); height: calc(100% - 8px); border-radius: 999px; background: var(--gold); transition: transform .38s cubic-bezier(.22, 1.2, .36, 1); }
.switch-pill.right { transform: translateX(100%); }
.switch-option { position: relative; z-index: 1; min-width: 88px; padding: 9px 20px; border: 0; border-radius: 999px; color: var(--text-secondary); background: transparent; font-weight: 700; cursor: pointer; transition: color .3s ease; }
.switch-option.active { color: var(--on-gold); }

.weekly-controls { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; align-items: end; padding: 20px; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); }
.weekly-controls label { display: grid; grid-template-columns: 1fr auto; gap: 9px; }
.weekly-controls input { grid-column: 1 / -1; accent-color: var(--gold); }
.weekly-controls strong { color: var(--accent-text); }
.weekly-controls button { padding: 12px 16px; border: 0; border-radius: var(--radius-md); color: var(--on-gold); background: var(--gold); font-weight: 700; cursor: pointer; }
.gen-hint { grid-column: 1 / -1; color: var(--muted); font-size: .78rem; }

/* 方案进度统计 */
.stats-panel { display: grid; gap: 14px; margin: 18px 0; padding: 20px; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); }
.stats-head { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.stats-head h2 { margin: 0; font-size: 1.1rem; }
.complete-chip { padding: 5px 11px; border-radius: 999px; color: var(--done-chip-text); background: var(--done-chip-bg); font-weight: 700; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.stats-grid article { display: grid; gap: 8px; padding: 15px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-muted); }
.stats-grid small { color: var(--accent-text); }
.stats-grid strong { font-size: 1.02rem; }
.stats-grid em { color: var(--muted); font-style: normal; font-size: .8rem; }
.bar { height: 8px; border-radius: 999px; background: var(--line); overflow: hidden; }
.bar i { display: block; height: 100%; border-radius: 999px; background: var(--gold); transition: width .8s cubic-bezier(.22, 1, .36, 1); }
.bar i.relic { background: var(--text-secondary); }
.weekly-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 18px 0; }
.weekly-summary article { display: grid; gap: 8px; padding: 17px; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); }
.weekly-summary small { color: var(--accent-text); letter-spacing: .1em; }
.weekly-summary strong { font-size: 1.05rem; }
.task-list { display: grid; gap: 10px; }
.task-list article { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 14px; padding: 16px; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); }
.task-list article.weekly { border-color: var(--boss-line); background: var(--boss-tint); }
.task-list article.completed { opacity: .55; }
.task-list article.completed .task-title strong { text-decoration: line-through; }
.check { width: 32px; height: 32px; border: 1px solid var(--line-strong); border-radius: var(--radius-md); color: var(--on-gold); background: var(--gold); font-weight: 900; cursor: pointer; }
.task-title { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.task-title span, .task-title em { padding: 4px 7px; border-radius: 999px; color: var(--text-secondary); background: var(--surface-muted); font-size: .75rem; font-style: normal; }
.progress-chip { color: var(--accent-text) !important; }
.task-list p { margin: 8px 0; color: var(--muted); }
.target-list { display: flex; flex-wrap: wrap; gap: 7px; }
.target-list a, .target-list span { padding: 6px 8px; color: var(--text-secondary); background: var(--surface-muted); text-decoration: none; }
.target-list b { color: var(--gold); }
.plan-notice { margin-top: 18px; padding: 17px; border-left: 3px solid var(--gold); background: var(--notice-tint); }
.plan-notice p, .plan-notice small { color: var(--muted); }
.empty-hint { margin: 26px 0; color: var(--muted); }

/* 今日视图 */
.daily-view { display: grid; gap: 16px; }
.day-picker { display: flex; flex-wrap: wrap; gap: 8px; }
.day-chip { display: grid; gap: 2px; justify-items: center; min-width: 62px; padding: 9px 12px; border: 1px solid var(--line); border-radius: var(--radius-md); color: var(--text-secondary); background: var(--panel); font-weight: 600; cursor: pointer; transition: border-color .25s ease, transform .25s ease, background .25s ease; }
.day-chip small { color: var(--gold); font-size: .68rem; }
.day-chip:hover { transform: translateY(-2px); }
.day-chip.active { border-color: var(--gold); background: var(--chip-active-tint); color: var(--accent-text); }

.daily-summary { display: flex; flex-wrap: wrap; gap: 22px; align-items: center; padding: 20px; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); transition: opacity .3s ease; }
.daily-summary.loading { opacity: .6; }
.ring-wrap { position: relative; width: 128px; height: 128px; flex: none; }
.ring { width: 100%; height: 100%; transform: rotate(-90deg); }
.ring-track { fill: none; stroke: var(--line); stroke-width: 10; }
.ring-value { fill: none; stroke: var(--gold); stroke-width: 10; stroke-linecap: round; transition: stroke-dashoffset .9s cubic-bezier(.22, 1, .36, 1); }
.ring-center { position: absolute; inset: 0; display: grid; gap: 2px; place-content: center; text-align: center; }
.ring-center strong { font-size: 1.5rem; color: var(--accent-text); }
.ring-center small { color: var(--muted); }
.daily-meta { display: grid; gap: 8px; min-width: min(420px, 100%); }
.daily-meta h2 { margin: 0; }
.daily-meta p { margin: 0; color: var(--muted); }
.daily-notice { color: var(--accent-text); }

.daily-list { display: grid; gap: 10px; }
.daily-card { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 14px; padding: 16px; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--panel); }
.daily-card.boss { border-color: var(--boss-line); background: var(--boss-tint); }
.daily-card.done { opacity: .62; }
.daily-card.done .task-title strong { text-decoration: line-through; }
.boss-badge { padding: 4px 9px !important; color: var(--on-gold) !important; background: var(--gold) !important; font-weight: 800; }
.rec-badge { padding: 4px 9px !important; color: var(--accent-text) !important; border: 1px solid var(--line-strong); background: transparent !important; font-weight: 700; }
.done-chip { color: var(--done-chip-text) !important; background: var(--done-chip-bg) !important; font-weight: 700; }

/* 视图切换与卡片级联动画 */
.view-enter-active { transition: opacity .4s cubic-bezier(.22, 1, .36, 1), transform .4s cubic-bezier(.22, 1, .36, 1); }
.view-leave-active { transition: opacity .2s ease, transform .2s ease; }
.view-enter-from { opacity: 0; transform: translateY(16px); }
.view-leave-to { opacity: 0; transform: translateY(-10px); }
.slice-enter-active { transition: opacity .45s cubic-bezier(.22, 1, .36, 1), transform .45s cubic-bezier(.22, 1, .36, 1); transition-delay: var(--stagger, 0ms); }
.slice-enter-from { opacity: 0; transform: translateY(14px); }

@media (prefers-reduced-motion: reduce) {
  .switch-pill, .ring-value, .day-chip, .view-enter-active, .view-leave-active, .slice-enter-active { transition: none !important; }
}

@media (max-width: 800px) {
  .weekly-head { grid-template-columns: 1fr; align-items: start; }
  .head-side { justify-items: start; }
  .weekly-controls { grid-template-columns: 1fr; }
  .weekly-summary { grid-template-columns: 1fr; }
}
</style>
