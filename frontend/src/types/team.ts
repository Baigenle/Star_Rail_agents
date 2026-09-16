import type { AIResponse } from './ai'

export interface OfficialTeamMember {
  character_id: string
  name: string
  element: string
  roles: string[]
  mechanic_tags: string[]
  image_url?: string | null
}

export interface TeamScenarioScore {
  scenario_id: string
  name: string
  score: number
}

export interface TeamScoreBreakdown {
  scoring_version: string
  game_data_version: string
  structural_score: number
  mechanical_simulation_score: number
  observed_meta_score?: number | null
  evidence_confidence: number
  final_score: number
  scenarios: TeamScenarioScore[]
}

export interface TeamRotationSummary {
  skill_point_balance: number
  estimated_ultimate_turns: Record<string, number | null>
  speed_order: string[]
}

export interface RecommendedOfficialTeam {
  members: OfficialTeamMember[]
  score: number
  covered_roles: string[]
  reasons: string[]
  strengths: string[]
  weaknesses: string[]
  source_character_ids: string[]
  preferred_character_ids: string[]
  missing_character_ids: string[]
  model_assessment?: string | null
  model_verdict?: string | null
  score_breakdown?: TeamScoreBreakdown | null
  rotation?: TeamRotationSummary | null
  data_warnings: string[]
}

export interface OfficialTeamResult {
  response: AIResponse
  theoretical: RecommendedOfficialTeam[]
  owned: RecommendedOfficialTeam[]
  favorite_trials: RecommendedOfficialTeam[]
}

export interface SavedTeam {
  id: string
  name: string
  members: OfficialTeamMember[]
  created_at: string
  updated_at: string
}
