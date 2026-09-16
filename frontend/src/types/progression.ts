import type { RelatedItem } from './catalog'

export interface SkillRange {
  from_level: number
  to_level: number
}

export interface ProgressionTrack {
  label: string
  max_level: number
}

export interface ProgressionProfile {
  character_id: string
  archetype: 'standard' | 'elation' | 'remembrance'
  tracks: Record<string, ProgressionTrack>
  ascension_gates: number[]
}

export interface ProgressionMaterial {
  key: string
  quantity: number
  item: RelatedItem | null
}

export interface ProgressionCalculation {
  character_id: string
  archetype: string
  from_level: number
  to_level: number
  skill_ranges: Record<string, SkillRange>
  total_by_key: Record<string, number>
  materials: ProgressionMaterial[]
}

export interface CharacterProgress {
  character_id: string
  current_level: number
  target_level: number
  eidolon: number
  current_skills: Record<string, number>
  target_skills: Record<string, number>
  created_at: string
  updated_at: string
}
