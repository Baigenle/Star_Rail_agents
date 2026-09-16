<script lang="ts">
export interface TourStep {
  /** 目标元素的 data-tour 键；缺省时显示为居中卡片 */
  target?: string
  title: string
  content: string
  buttonLabel?: string
}
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ steps: TourStep[] }>()
const emit = defineEmits<{ finish: [] }>()

const SPOT_PADDING = 8
const VIEWPORT_GAP = 16
const CARD_WIDTH = 340
const CARD_GAP = 14

const index = ref(-1)
const spot = ref({ top: 0, left: 0, width: 0, height: 0 })
const cardStyle = ref<{ top: string; left: string }>({ top: '50%', left: '50%' })
const centered = ref(true)
const ready = ref(false)
const cardRef = ref<HTMLElement | null>(null)

const step = computed(() =>
  index.value >= 0 ? props.steps[index.value] ?? null : null,
)
const isLast = computed(() => index.value === props.steps.length - 1)

function targetElement(key: string | undefined) {
  return key
    ? document.querySelector<HTMLElement>(`[data-tour="${key}"]`)
    : null
}

function isOffscreen(element: HTMLElement) {
  const rect = element.getBoundingClientRect()
  return (
    rect.width === 0
    || rect.height === 0
    || rect.right <= 0
    || rect.bottom <= 0
    || rect.left >= window.innerWidth
    || rect.top >= window.innerHeight
  )
}

function placeCenteredCard() {
  centered.value = true
  const height = cardRef.value?.offsetHeight ?? 170
  cardStyle.value = {
    left: `${Math.max(VIEWPORT_GAP, (window.innerWidth - CARD_WIDTH) / 2)}px`,
    top: `${Math.max(VIEWPORT_GAP, (window.innerHeight - height) / 2)}px`,
  }
}

function placeAnchoredCard(rect: DOMRect) {
  centered.value = false
  const width = Math.min(CARD_WIDTH, window.innerWidth - VIEWPORT_GAP * 2)
  const height = cardRef.value?.offsetHeight ?? 170
  // 依次尝试下方、上方、右侧、左侧，都放不下再夹回视口。
  const fitsBelow = rect.bottom + CARD_GAP + height <= window.innerHeight - VIEWPORT_GAP
  const fitsAbove = rect.top - CARD_GAP - height >= VIEWPORT_GAP
  const fitsRight = rect.right + CARD_GAP + width <= window.innerWidth - VIEWPORT_GAP
  const fitsLeft = rect.left - CARD_GAP - width >= VIEWPORT_GAP
  let left: number
  let top: number
  if (fitsBelow) {
    left = rect.left
    top = rect.bottom + CARD_GAP
  } else if (fitsAbove) {
    left = rect.left
    top = rect.top - CARD_GAP - height
  } else if (fitsRight) {
    left = rect.right + CARD_GAP
    top = rect.top + rect.height / 2 - height / 2
  } else if (fitsLeft) {
    left = rect.left - CARD_GAP - width
    top = rect.top + rect.height / 2 - height / 2
  } else {
    left = rect.left
    top = rect.bottom + CARD_GAP
  }
  left = Math.min(Math.max(VIEWPORT_GAP, left), window.innerWidth - width - VIEWPORT_GAP)
  top = Math.min(Math.max(VIEWPORT_GAP, top), window.innerHeight - height - VIEWPORT_GAP)
  cardStyle.value = { left: `${left}px`, top: `${top}px` }
}

function advance() {
  if (isLast.value) emit('finish')
  else index.value += 1
}

async function applyStep() {
  const current = step.value
  if (!current) {
    emit('finish')
    return
  }
  ready.value = false
  await nextTick()
  if (!current.target) {
    placeCenteredCard()
    ready.value = true
    await nextTick()
    placeCenteredCard()
    return
  }
  const element = targetElement(current.target)
  // 目标元素当前不可见（如窄屏下隐藏的会话历史）时跳过该步。
  if (!element || isOffscreen(element)) {
    advance()
    return
  }
  element.scrollIntoView({ block: 'center', inline: 'nearest' })
  const rect = element.getBoundingClientRect()
  const top = Math.max(VIEWPORT_GAP, rect.top - SPOT_PADDING)
  const left = Math.max(VIEWPORT_GAP, rect.left - SPOT_PADDING)
  const right = Math.min(window.innerWidth - VIEWPORT_GAP, rect.right + SPOT_PADDING)
  const bottom = Math.min(window.innerHeight - VIEWPORT_GAP, rect.bottom + SPOT_PADDING)
  spot.value = { top, left, width: right - left, height: bottom - top }
  placeAnchoredCard(rect)
  ready.value = true
  await nextTick()
  placeAnchoredCard(element.getBoundingClientRect())
}

function reposition() {
  const current = step.value
  if (!current || !ready.value) return
  if (!current.target) {
    placeCenteredCard()
    return
  }
  const element = targetElement(current.target)
  if (!element) return
  const rect = element.getBoundingClientRect()
  const top = Math.max(VIEWPORT_GAP, rect.top - SPOT_PADDING)
  const left = Math.max(VIEWPORT_GAP, rect.left - SPOT_PADDING)
  const right = Math.min(window.innerWidth - VIEWPORT_GAP, rect.right + SPOT_PADDING)
  const bottom = Math.min(window.innerHeight - VIEWPORT_GAP, rect.bottom + SPOT_PADDING)
  spot.value = { top, left, width: right - left, height: bottom - top }
  placeAnchoredCard(rect)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('finish')
}

onMounted(() => {
  if (!props.steps.length) {
    emit('finish')
    return
  }
  index.value = 0
  window.addEventListener('resize', reposition)
  // capture 阶段监听才能收到工作区内部滚动容器的滚动事件。
  window.addEventListener('scroll', reposition, true)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', reposition)
  window.removeEventListener('scroll', reposition, true)
  window.removeEventListener('keydown', onKeydown)
})

watch(index, () => {
  void applyStep()
})
</script>

<template>
  <div
    class="tour-overlay"
    :class="{ 'tour-overlay--dim': centered }"
    role="dialog"
    aria-modal="true"
    :aria-label="step?.title"
    @click="advance"
  >
    <div
      v-if="step?.target && ready"
      class="tour-spot"
      :style="{
        top: `${spot.top}px`,
        left: `${spot.left}px`,
        width: `${spot.width}px`,
        height: `${spot.height}px`,
      }"
    />
    <div
      v-if="ready"
      ref="cardRef"
      class="tour-card"
      :class="{ 'tour-card--center': centered }"
      :style="cardStyle"
      @click.stop
    >
      <p class="tour-step-tag">TOUR · {{ index + 1 }} / {{ steps.length }}</p>
      <h3>{{ step?.title }}</h3>
      <p class="tour-text">{{ step?.content }}</p>
      <div class="tour-actions">
        <button type="button" class="tour-skip" @click="emit('finish')">跳过引导</button>
        <button type="button" class="tour-next" @click="advance">
          {{ step?.buttonLabel ?? (isLast ? '完成' : '下一步') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tour-overlay {
  position: fixed;
  inset: 0;
  z-index: 90;
  background: transparent;
  transition: background .3s ease;
}
.tour-overlay--dim { background: rgba(4, 6, 11, .74); }
.tour-spot {
  position: fixed;
  border-radius: 14px;
  pointer-events: none;
  box-shadow:
    0 0 0 2px rgba(233, 200, 117, .6),
    0 0 0 9999px rgba(4, 6, 11, .74),
    0 0 36px rgba(233, 200, 117, .22);
  transition: top .28s ease, left .28s ease, width .28s ease, height .28s ease;
  animation: tour-fade-in .25s ease;
}
.tour-card {
  position: fixed;
  width: min(340px, calc(100vw - 32px));
  padding: 16px 18px 14px;
  border: 1px solid var(--line-strong);
  border-radius: 14px;
  background: linear-gradient(165deg, rgba(26, 28, 32, .98), rgba(14, 16, 19, .98));
  box-shadow: 0 26px 70px rgba(0, 0, 0, .55);
  transition: top .28s ease, left .28s ease;
  animation: tour-fade-in .25s ease;
}
.tour-card--center { border-color: var(--gold); }
.tour-step-tag { margin: 0; color: var(--gold); font-size: 10px; letter-spacing: .22em; }
.tour-card h3 { margin: 7px 0 8px; font-size: 1.02rem; letter-spacing: -.01em; }
.tour-text { margin: 0; color: var(--text-secondary); font-size: .87rem; line-height: 1.75; }
.tour-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 16px;
}
.tour-skip {
  border: 0;
  padding: 4px 2px;
  background: transparent;
  color: var(--muted);
  font-size: .8rem;
  cursor: pointer;
}
.tour-skip:hover { color: var(--text-secondary); }
.tour-next {
  border: 0;
  border-radius: var(--radius-sm);
  padding: 8px 18px;
  color: #24211b;
  background: var(--gold);
  font-size: .85rem;
  cursor: pointer;
}
.tour-next:hover { background: var(--focus); }
@keyframes tour-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
