export interface Claim {
  statement: string
  confidence: number
  citation_ids: string[]
}

export interface Citation {
  id: string
  title: string
  source: string
  excerpt: string
  document_id?: string
  chunk_id?: string
  game_version?: string
  updated_at?: string
  relevance_score?: number
  image_url?: string
  entity_url?: string
}

export interface AgentAction {
  action_type: 'navigate' | 'prefill'
  title: string
  target_url: string
  description?: string
  params?: Record<string, string>
}

export interface AIResponse {
  response_id: string
  agent: string
  protocol: 'claim-citation-validation-filtering'
  answer: string
  claims: Claim[]
  citations: Citation[]
  validation: {
    status: 'verified' | 'partially_verified' | 'unverified' | 'conflicted'
    method: string
    evidence_count: number
    notes: string[]
  }
  filtering: {
    passed: boolean
    removed_claims: number
    rules: string[]
    warnings: string[]
  }
  query_steps: Array<{
    id: string
    name: string
    status: 'completed' | 'fallback' | 'failed'
    detail: string
    duration_ms?: number
  }>
  invoked_agents: string[]
  conversation_id?: string
  memory_suggestions: MemorySuggestion[]
  favorite_character_suggestions: FavoriteCharacterSuggestion[]
  related_entities: RelatedEntity[]
  actions?: AgentAction[]
  follow_up_questions?: string[]
}

export type MemoryType =
  | 'playstyle_preference'
  | 'resource_priority'
  | 'favorite_character'
  | 'usual_team'
  | 'answer_preference'

export interface MemorySuggestion {
  memory_type: MemoryType
  content: string
  reason: string
}

export interface FavoriteCharacterSuggestion {
  character_id: string
  name: string
  is_owned: boolean
  prompt: string
}

export interface RelatedEntity {
  entity_type: 'character' | 'item' | 'lightcone' | 'relic' | 'story' | 'activity'
  entity_id: string
  name: string
  entity_url: string
  image_url?: string | null
}

export interface ChatJob {
  id: string
  conversation_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  message: string
  response?: AIResponse | null
  partial_answer: string
  progress: {
    stage?: string
    percent?: number
    agent?: string
  }
  error_message?: string | null
  created_at: string
  updated_at: string
  completed_at?: string | null
}

export interface ChatJobEvent {
  sequence: number
  event_type:
    | 'job.queued'
    | 'job.running'
    | 'intent.started'
    | 'intent.completed'
    | 'agent.selected'
    | 'agent.started'
    | 'agent.completed'
    | 'retrieval.started'
    | 'retrieval.completed'
    | 'validation.completed'
    | 'filtering.completed'
    | 'answer.delta'
    | 'answer.completed'
    | 'job.completed'
    | 'job.failed'
    | 'job.recovered'
    | 'fc.started'
    | 'fc.round'
    | 'fc.round_timeout'
    | 'fc.tool_started'
    | 'fc.tool_result'
    | 'fc.summary'
    | 'fc.fallback'
    | 'fc.error'
    | 'fc.completed'
    | 'task_submitted'
    | 'task_completed'
    | 'orchestration.started'
    | 'orchestration.completed'
    | 'react.route'
    | 'react.thought'
    | 'react.tool_started'
    | 'react.tool_completed'
    | 'react.clarification'
    | 'react.integrating'
    | 'react.error'
  agent?: string | null
  title: string
  detail: string
  status: string
  duration_ms?: number | null
  payload: {
    delta?: string
    evidence_count?: number
    validation_status?: string
    passed?: boolean
    removed_claims?: number
    invoked_agents?: string[]
  }
  created_at: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface StoredChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  response?: AIResponse
  created_at: string
}

export interface MemoryRecord {
  id: string
  memory_type: MemoryType
  content: string
  source: string
  is_active: boolean
  created_at: string
  updated_at: string
}
