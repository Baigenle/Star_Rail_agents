export interface StorySummary {
  mission_id: string
  mission_name: string
  mission_type: string
  version: string
  world: string
  series_name: string
  mission_order: number
  characters: string[]
  summary: string
  scene_count: number
  matched_character?: string | null
  matched_scene_count?: number
  first_matching_chunk_id?: string | null
}

export interface StoryFilters {
  versions: string[]
  worlds: string[]
  mission_types: string[]
  series: string[]
}

export interface StorySceneSummary {
  chunk_id: string
  chunk_order: number
  scene_title: string
  location?: string | null
  characters: string[]
}

export interface StoryDetail extends StorySummary {
  story_text: string
  source_url: string
  previous_mission?: string | null
  next_mission?: string | null
  scenes: StorySceneSummary[]
}

export interface StoryScene extends StorySceneSummary {
  mission_id: string
  mission_name: string
  content: string
  source_url: string
  previous_chunk_id?: string | null
  next_chunk_id?: string | null
}
