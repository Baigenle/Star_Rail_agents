export interface AIAssessment {
  decision: 'advisory_only'
  completeness: {
    passed: boolean
    score: number
    missing_fields: string[]
  }
  consistency_warnings: string[]
  numerical_risks: string[]
  official_lore_risks: string[]
  suggestions: string[]
  model_used: boolean
  generated_at: string
}

export interface ModerationItem {
  content_type: 'character' | 'activity_guide'
  content_id: string
  title: string
  status: string
  author_name: string
  reason?: string | null
  updated_at: string
}
