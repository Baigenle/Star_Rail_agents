export interface ActivityImage {
  source_url: string
  api_path?: string
  availability: string
}

export interface ActivitySummary {
  id: string
  title: string
  version: string
  schedule: string
  types: string[]
  tags: string[]
  image?: ActivityImage | null
  detail_available: boolean
  official_guide_available: boolean
  community_submission_available: boolean
}

export interface ActivityDetail extends ActivitySummary {
  detail?: { sections: Array<{ title: string; paragraphs: string[] }> } | null
  source: { url?: string; content_id?: string }
}

export interface ActivityGuide {
  id: string
  activity_id: string
  activity_title: string
  author_id: string
  author_name: string
  title: string
  content: string
  player_stage: string
  status: string
  review_reason?: string | null
  submitted_at: string
  reviewed_at?: string | null
}
