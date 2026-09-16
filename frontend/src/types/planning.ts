import type { AIResponse } from './ai'
import type { CharacterSummary } from './catalog'
import type { ProgressionCalculation, SkillRange } from './progression'

export interface CharacterPlanInput {
  character_id: string
  from_level: number
  to_level: number
  skill_ranges: Record<string, SkillRange>
}

export interface BuildRecommendation {
  lightcones: Array<{ id: string; name: string; image_url?: string }>
  tunnel_relics: Array<{ id: string; name: string; image_url?: string }>
  planar_relics: Array<{ id: string; name: string; image_url?: string }>
  skill_priority: string[]
  warnings: string[]
}

export interface MultiProgressionResult {
  response: AIResponse
  characters: ProgressionCalculation[]
  total_by_key: Record<string, number>
  materials: ProgressionCalculation['materials']
  recommendations: Record<string, BuildRecommendation>
}

export interface ProgressionPlanProgress {
  scheduled_runs: number
  completed_runs: number
  required_scheduled: number
  required_completed: number
  in_current_window: boolean
  complete: boolean
}

export interface ProgressionPlan {
  id: string
  name: string
  status: 'active' | 'paused' | 'completed'
  priority: number
  request_payload: { characters: CharacterPlanInput[] }
  material_snapshot: MultiProgressionResult
  recommendation_snapshot: Record<string, BuildRecommendation>
  progress: ProgressionPlanProgress
  created_at: string
  updated_at: string
}

export interface PlannerRow {
  character: CharacterSummary
  fromLevel: number
  toLevel: number
  tracks: Record<string, { label: string; maxLevel: number; from: number; to: number }>
}

export interface WeeklyMaterialTarget {
  key: string
  name: string
  required_quantity: number
  item_id?: string
  entity_url?: string
}

export interface WeeklyTask {
  id: string
  title: string
  detail: string
  dungeon_type: '历战余响' | '拟造花萼（金）' | '拟造花萼（赤）' | '凝滞虚影' | '侵蚀隧洞' | '无体力来源'
  stamina_per_run: number
  run_count: number
  stamina_cost: number
  priority: number
  completed: boolean
  completed_runs: number
  is_required: boolean
  targets: WeeklyMaterialTarget[]
  source_plan_ids: string[]
}

export interface PlanProgressEntry {
  plan_id: string
  plan_name: string
  scheduled_runs: number
  completed_runs: number
}

export interface WeeklyStatistics {
  required_scheduled: number
  required_completed: number
  recommended_scheduled: number
  recommended_completed: number
  plan_complete: boolean
  plans: PlanProgressEntry[]
}

export interface WeeklyPlan {
  id: string
  week_start: string
  week_end: string
  stamina_budget: number
  allocated_stamina: number
  weekly_runs_remaining: number
  tasks: WeeklyTask[]
  statistics: WeeklyStatistics
  notice: string
  evidence_version: string
  created_at: string
  updated_at: string
}

export interface DailyTaskSlice {
  weekly_task_id: string
  title: string
  dungeon_type: WeeklyTask['dungeon_type']
  stamina_per_run: number
  run_count_week: number
  runs_planned: number
  stamina: number
  completed: boolean
  is_weekly_boss: boolean
  is_required: boolean
  priority: number
  targets: WeeklyMaterialTarget[]
}

export interface DailyPlan {
  date: string
  weekday_label: string
  week_start: string
  week_end: string
  week_day_index: number
  remaining_days: number
  stamina_cap: number
  planned_stamina: number
  completed_stamina: number
  weekly_budget: number
  weekly_allocated: number
  weekly_runs_remaining: number
  items: DailyTaskSlice[]
  notice: string
  evidence_version: string
}
