import type { AIResponse } from './ai'

export interface CustomBaseStats {
  hp: number
  attack: number
  defence: number
  speed: number
  taunt: number
  energy: number
}

export interface CustomCharacterPayload {
  name?: string
  rarity?: 4 | 5
  element?: string
  path?: string
  summary?: string
  roles: string[]
  core_mechanics?: string
  mechanic_tags: string[]
  base_stats?: CustomBaseStats
  skills: Record<string, string>
  special_skills: Record<string, string>
  story?: string
  eidolons: string[]
}

export interface CustomCharacter {
  id: string
  author_id: string
  author_name: string
  name: string
  visibility: string
  version_id: string
  version_number: number
  status: string
  payload: CustomCharacterPayload
  review_reason?: string
  is_owner: boolean
  created_at: string
  updated_at: string
}

export interface CreatorSession {
  id: string
  character_id: string
  stage: number
  status: string
  pending_fields: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface CreatorTurn {
  response: AIResponse
  character_id: string
  session_id: string
  stage: number
  draft: CustomCharacterPayload
  pending_fields: Record<string, unknown>
  required_fields: string[]
}

export interface TeamMember {
  character_id: string
  name: string
  element: string
  roles: string[]
  is_custom: boolean
}

export interface RecommendedTeam {
  members: TeamMember[]
  score: number
  covered_roles: string[]
  reasons: string[]
  source_character_ids: string[]
}

export interface CustomTeamResult {
  response: AIResponse
  theoretical: RecommendedTeam[]
  owned: RecommendedTeam[]
}

export type SelfReviewSeverity = 'error' | 'warning' | 'suggestion'
export type SelfReviewVerdict = 'ready' | 'needs_work' | 'rejected'
export type SelfReviewCategoryKey =
  | 'completeness'
  | 'authenticity'
  | 'consistency'
  | 'balance'
  | 'compliance'

export interface SelfReviewIssue {
  code: string
  severity: SelfReviewSeverity
  field: string
  description: string
  suggestion: string
}

export interface SelfReviewCategory {
  key: SelfReviewCategoryKey
  name: string
  score: number
  max_score: 100
  weight: number
  issues: SelfReviewIssue[]
}

export interface SelfReviewReport {
  overall_score: number
  verdict: SelfReviewVerdict
  summary: string
  categories: SelfReviewCategory[]
  highlights: string[]
  must_fix_count: number
  warn_count: number
  model_used: boolean
  generated_at: string
}
