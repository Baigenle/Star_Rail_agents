import axios from 'axios'
import type { AIResponse, ChatJob, ChatJobEvent, Conversation, MemoryRecord, MemoryType, StoredChatMessage } from '../types/ai'
import type { AuthResponse, UserProfile } from '../types/auth'
import type { CharacterDetail, CharacterSummary, ItemDetail, KnowledgeEntityDetail, KnowledgeEntitySummary, LightconeDetail, RelicDetail } from '../types/catalog'
import type { CharacterPool, UserCharacter } from '../types/profile'
import type { CharacterProgress, ProgressionCalculation, ProgressionProfile, SkillRange } from '../types/progression'
import type { CreatorSession, CreatorTurn, CustomCharacter, CustomCharacterPayload, CustomTeamResult, SelfReviewReport } from '../types/customCharacter'
import type { OfficialTeamResult, SavedTeam } from '../types/team'
import type { CharacterPlanInput, DailyPlan, MultiProgressionResult, ProgressionPlan, WeeklyPlan } from '../types/planning'
import type { ActivityDetail, ActivityGuide, ActivitySummary } from '../types/activity'
import type { AIAssessment, ModerationItem } from '../types/moderation'
import type { StoryDetail, StoryFilters, StoryScene, StorySummary } from '../types/story'
import { buildChatRequestPayload } from '../utils/chatRequestPayload'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1',
  timeout: 30_000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('star_rail_access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export async function sendMessage(
  message: string,
  conversationId?: string,
  history: Array<{ role: 'user' | 'assistant'; content: string }> = [],
): Promise<AIResponse> {
  const { data } = await api.post<AIResponse>(
    '/chat/messages',
    buildChatRequestPayload(message, conversationId, history),
    { timeout: 120_000 },
  )
  return data
}

export async function createChatJob(
  message: string,
  conversationId?: string,
  history: Array<{ role: 'user' | 'assistant'; content: string }> = [],
): Promise<ChatJob> {
  const { data } = await api.post<ChatJob>(
    '/chat/jobs',
    buildChatRequestPayload(message, conversationId, history),
  )
  return data
}

export async function getChatJobs(status?: ChatJob['status']): Promise<ChatJob[]> {
  const { data } = await api.get<{ items: ChatJob[] }>('/chat/jobs', {
    params: status ? { status } : undefined,
  })
  return data.items
}

export async function getChatJob(id: string): Promise<ChatJob> {
  const { data } = await api.get<ChatJob>(`/chat/jobs/${id}`)
  return data
}

export async function retryChatJob(id: string): Promise<ChatJob> {
  const { data } = await api.post<ChatJob>(`/chat/jobs/${id}/retry`)
  return data
}

export async function streamChatJobEvents(
  id: string,
  onEvent: (event: ChatJobEvent) => void,
  signal: AbortSignal,
  lastEventId = 0,
): Promise<void> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
  const token = localStorage.getItem('star_rail_access_token')
  const response = await fetch(`${baseUrl}/chat/jobs/${id}/events`, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(lastEventId ? { 'Last-Event-ID': String(lastEventId) } : {}),
    },
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`事件流连接失败：${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n')
      if (data) onEvent(JSON.parse(data) as ChatJobEvent)
      boundary = buffer.indexOf('\n\n')
    }
    if (done) break
  }
}

export async function getConversations(): Promise<Conversation[]> {
  const { data } = await api.get<{ items: Conversation[] }>('/chat/conversations')
  return data.items
}

export async function getConversationMessages(
  conversationId: string,
): Promise<{ conversation: Conversation; items: StoredChatMessage[] }> {
  const { data } = await api.get(`/chat/conversations/${conversationId}/messages`)
  return data
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await api.delete(`/chat/conversations/${conversationId}`)
}

export async function getMemories(): Promise<MemoryRecord[]> {
  const { data } = await api.get<{ items: MemoryRecord[] }>('/profile/memories')
  return data.items
}

export async function createMemory(
  memoryType: MemoryType,
  content: string,
): Promise<MemoryRecord> {
  const { data } = await api.post<MemoryRecord>('/profile/memories', {
    memory_type: memoryType,
    content,
    source: 'chat_suggestion',
  })
  return data
}

export async function updateMemory(
  id: string,
  payload: Partial<Pick<MemoryRecord, 'memory_type' | 'content' | 'is_active'>>,
): Promise<MemoryRecord> {
  const { data } = await api.patch<MemoryRecord>(`/profile/memories/${id}`, payload)
  return data
}

export async function deleteMemory(id: string): Promise<void> {
  await api.delete(`/profile/memories/${id}`)
}

export async function getCharacters(): Promise<CharacterSummary[]> {
  const { data } = await api.get<{ items: CharacterSummary[] }>('/catalog/characters')
  return data.items
}

export async function getCharacter(id: string): Promise<CharacterDetail> {
  const { data } = await api.get<CharacterDetail>(`/catalog/characters/${id}`)
  return data
}

export async function getItem(id: string): Promise<ItemDetail> {
  const { data } = await api.get<ItemDetail>(`/catalog/items/${id}`)
  return data
}

export async function getLightcone(id: string): Promise<LightconeDetail> {
  const { data } = await api.get<LightconeDetail>(`/catalog/lightcones/${id}`)
  return data
}

export async function getRelic(id: string): Promise<RelicDetail> {
  const { data } = await api.get<RelicDetail>(`/catalog/relics/${id}`)
  return data
}

export async function getKnowledgeEntities(kind: string): Promise<KnowledgeEntitySummary[]> {
  const { data } = await api.get<{ items: Array<KnowledgeEntitySummary & { type?: string; rarity?: number | string }> }>(`/catalog/${kind}`)
  if (kind === 'items') {
    const rarityMap: Record<string, number> = { Normal: 1, NotNormal: 2, Rare: 3, VeryRare: 4, SuperRare: 5 }
    return data.items.map((item) => ({
      ...item,
      kind: 'items',
      rarity: typeof item.rarity === 'number' ? item.rarity : rarityMap[String(item.rarity)] ?? 0,
      subtitle: item.type ?? '物品',
      image_status: item.image_url?.includes('placeholders') ? 'category_placeholder' : 'official',
    })) as KnowledgeEntitySummary[]
  }
  return data.items
}

export async function getKnowledgeEntity(kind: string, id: string): Promise<KnowledgeEntityDetail> {
  const { data } = await api.get<KnowledgeEntityDetail>(`/catalog/${kind}/${id}`)
  return data
}

export async function registerUser(payload: { username: string; email: string; password: string; display_name: string }): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/auth/register', payload)
  return data
}

export async function loginUser(payload: { account: string; password: string }): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/auth/login', payload)
  return data
}

export async function getCurrentUser(): Promise<UserProfile> {
  const { data } = await api.get<UserProfile>('/auth/me')
  return data
}

export async function getCharacterPool(): Promise<CharacterPool> {
  const { data } = await api.get<CharacterPool>('/profile/characters')
  return data
}

export async function replaceCharacterPool(characterIds: string[]): Promise<CharacterPool> {
  const { data } = await api.put<CharacterPool>('/profile/characters', { character_ids: characterIds })
  return data
}

export async function setCharacterFavorite(characterId: string, isFavorite: boolean): Promise<UserCharacter> {
  const { data } = await api.patch<UserCharacter>(`/profile/characters/${characterId}/favorite`, {
    is_favorite: isFavorite,
  })
  return data
}

export async function getProgressionProfile(characterId: string): Promise<ProgressionProfile> {
  const { data } = await api.get<ProgressionProfile>(`/catalog/characters/${characterId}/progression`)
  return data
}

export async function calculateProgression(
  characterId: string,
  payload: { from_level: number; to_level: number; skill_ranges: Record<string, SkillRange> },
): Promise<ProgressionCalculation> {
  const { data } = await api.post<ProgressionCalculation>(
    `/catalog/characters/${characterId}/progression/calculate`,
    payload,
  )
  return data
}

export async function getSavedProgression(characterId: string): Promise<CharacterProgress> {
  const { data } = await api.get<CharacterProgress>(`/profile/characters/${characterId}/progression`)
  return data
}

export async function saveProgression(
  characterId: string,
  payload: Omit<CharacterProgress, 'character_id' | 'created_at' | 'updated_at'>,
): Promise<CharacterProgress> {
  const { data } = await api.put<CharacterProgress>(
    `/profile/characters/${characterId}/progression`,
    payload,
  )
  return data
}

export async function createCustomCharacter(name?: string): Promise<CustomCharacter> {
  const { data } = await api.post<CustomCharacter>('/custom-characters', { name })
  return data
}

export async function getMyCustomCharacters(): Promise<CustomCharacter[]> {
  const { data } = await api.get<{ items: CustomCharacter[] }>('/custom-characters')
  return data.items
}

export async function getCustomCharacter(id: string): Promise<CustomCharacter> {
  const { data } = await api.get<CustomCharacter>(`/custom-characters/${id}`)
  return data
}

export async function updateCustomCharacter(id: string, payload: CustomCharacterPayload): Promise<CustomCharacter> {
  const { data } = await api.patch<CustomCharacter>(`/custom-characters/${id}`, { payload })
  return data
}

export async function createCreatorSession(id: string): Promise<CreatorSession> {
  const { data } = await api.post<CreatorSession>(`/custom-characters/${id}/sessions`)
  return data
}

export async function getLatestCreatorSession(id: string): Promise<CreatorSession> {
  const { data } = await api.get<CreatorSession>(`/custom-characters/${id}/sessions/latest`)
  return data
}

export async function sendCreatorMessage(
  sessionId: string,
  message: string,
  fields: Record<string, unknown>,
): Promise<CreatorTurn> {
  const { data } = await api.post<CreatorTurn>(`/custom-character-sessions/${sessionId}/messages`, { message, fields })
  return data
}

export async function confirmCreatorStage(sessionId: string): Promise<CreatorTurn> {
  const { data } = await api.post<CreatorTurn>(`/custom-character-sessions/${sessionId}/confirm-stage`)
  return data
}

export async function recommendCustomTeams(id: string): Promise<CustomTeamResult> {
  const { data } = await api.post<CustomTeamResult>(`/custom-characters/${id}/team-recommendations`)
  return data
}

export async function submitCustomCharacter(id: string): Promise<CustomCharacter> {
  const { data } = await api.post<CustomCharacter>(`/custom-characters/${id}/submit`)
  return data
}

export async function runCustomCharacterSelfReview(id: string): Promise<SelfReviewReport> {
  const { data } = await api.post<SelfReviewReport>(
    `/custom-characters/${id}/self-review`,
    undefined,
    { timeout: 120_000 },
  )
  return data
}

export async function getCustomCharacterSelfReview(id: string): Promise<SelfReviewReport> {
  const { data } = await api.get<SelfReviewReport>(`/custom-characters/${id}/self-review`)
  return data
}

export async function getCommunityCharacters(): Promise<CustomCharacter[]> {
  const { data } = await api.get<{ items: CustomCharacter[] }>('/community/characters')
  return data.items
}

export async function getCommunityCharacter(id: string): Promise<CustomCharacter> {
  const { data } = await api.get<CustomCharacter>(`/community/characters/${id}`)
  return data
}

export async function getPendingReviews(): Promise<CustomCharacter[]> {
  const { data } = await api.get<{ items: CustomCharacter[] }>('/admin/reviews')
  return data.items
}

export async function reviewCustomCharacter(versionId: string, action: 'approve' | 'reject', reason?: string): Promise<CustomCharacter> {
  const { data } = await api.post<CustomCharacter>(`/admin/reviews/${versionId}`, { action, reason })
  return data
}

export async function assessCustomCharacter(versionId: string): Promise<AIAssessment> {
  const { data } = await api.post<AIAssessment>(`/admin/reviews/${versionId}/ai-assessment`)
  return data
}

export async function getCommunityModeration(
  type: 'all' | 'character' | 'activity_guide',
  status: 'published' | 'unpublished',
): Promise<ModerationItem[]> {
  const { data } = await api.get<{ items: ModerationItem[] }>('/admin/community-moderation', {
    params: { type, status },
  })
  return data.items
}

export async function moderateCommunityCharacter(
  id: string,
  action: 'unpublish' | 'republish',
  reason = '',
): Promise<CustomCharacter> {
  const { data } = await api.post<CustomCharacter>(`/admin/community/characters/${id}/moderation`, {
    action,
    reason,
  })
  return data
}

export async function recommendOfficialTeams(payload: {
  core_character_id: string
  preferred_character_ids: string[]
  excluded_character_ids: string[]
  require_sustain: boolean
  use_owned_only: boolean
  game_mode: 'balanced' | 'moc' | 'pure_fiction' | 'apocalyptic'
}): Promise<OfficialTeamResult> {
  const { data } = await api.post<OfficialTeamResult>(
    '/teams/recommendations',
    payload,
    { timeout: 180_000 },
  )
  return data
}

export async function getSavedTeams(): Promise<SavedTeam[]> {
  const { data } = await api.get<{ items: SavedTeam[] }>('/profile/teams')
  return data.items
}

export async function saveOfficialTeam(name: string, memberIds: string[]): Promise<SavedTeam> {
  const { data } = await api.post<SavedTeam>('/profile/teams', { name, member_ids: memberIds })
  return data
}

export async function deleteSavedTeam(id: string): Promise<void> {
  await api.delete(`/profile/teams/${id}`)
}

export async function renameSavedTeam(id: string, name: string): Promise<SavedTeam> {
  const { data } = await api.patch<SavedTeam>(`/profile/teams/${id}`, { name })
  return data
}

export async function calculateMultiProgression(
  characters: CharacterPlanInput[],
): Promise<MultiProgressionResult> {
  const { data } = await api.post<MultiProgressionResult>(
    '/planning/progression/calculate',
    { characters },
  )
  return data
}

export async function getProgressionPlans(): Promise<ProgressionPlan[]> {
  const { data } = await api.get<{ items: ProgressionPlan[] }>('/profile/progression-plans')
  return data.items
}

export async function saveProgressionPlan(payload: {
  name: string
  priority: number
  characters: CharacterPlanInput[]
}): Promise<ProgressionPlan> {
  const { data } = await api.post<ProgressionPlan>('/profile/progression-plans', payload)
  return data
}

export async function updateProgressionPlan(
  id: string,
  payload: Partial<Pick<ProgressionPlan, 'name' | 'priority' | 'status'>>,
): Promise<ProgressionPlan> {
  const { data } = await api.patch<ProgressionPlan>(`/profile/progression-plans/${id}`, payload)
  return data
}

export async function deleteProgressionPlan(id: string): Promise<void> {
  await api.delete(`/profile/progression-plans/${id}`)
}

export async function generateWeeklyPlan(
  staminaBudget: number,
  weeklyRunsRemaining: number,
): Promise<WeeklyPlan> {
  const { data } = await api.post<WeeklyPlan>('/planning/weekly/generate', {
    stamina_budget: staminaBudget,
    weekly_runs_remaining: weeklyRunsRemaining,
  })
  return data
}

export async function getCurrentWeeklyPlan(): Promise<WeeklyPlan> {
  const { data } = await api.get<WeeklyPlan>('/profile/weekly-plans/current')
  return data
}

export async function updateWeeklyTask(
  planId: string,
  taskId: string,
  completed: boolean,
): Promise<WeeklyPlan> {
  const { data } = await api.patch<WeeklyPlan>(
    `/profile/weekly-plans/${planId}/tasks/${taskId}`,
    { completed },
  )
  return data
}

export async function getDailyPlan(date?: string): Promise<DailyPlan> {
  const { data } = await api.get<DailyPlan>('/planning/daily', {
    params: date ? { date } : undefined,
  })
  return data
}

export async function patchDailyTask(
  date: string,
  weeklyTaskId: string,
  completed: boolean,
): Promise<DailyPlan> {
  const { data } = await api.patch<DailyPlan>(
    `/planning/daily/${date}/${weeklyTaskId}`,
    { completed },
  )
  return data
}

export async function getActivities(version?: string): Promise<ActivitySummary[]> {
  const { data } = await api.get<{ items: ActivitySummary[] }>('/activities', {
    params: version ? { version } : undefined,
  })
  return data.items
}

export async function getActivity(id: string): Promise<ActivityDetail> {
  const { data } = await api.get<ActivityDetail>(`/activities/${id}`)
  return data
}

export async function getActivityGuides(id: string): Promise<ActivityGuide[]> {
  const { data } = await api.get<{ items: ActivityGuide[] }>(`/activities/${id}/guides`)
  return data.items
}

export async function submitActivityGuide(
  id: string,
  payload: { title: string; content: string; player_stage: string },
): Promise<ActivityGuide> {
  const { data } = await api.post<ActivityGuide>(`/activities/${id}/guides`, payload)
  return data
}

export async function getPendingActivityGuides(): Promise<ActivityGuide[]> {
  const { data } = await api.get<{ items: ActivityGuide[] }>('/admin/activity-guide-reviews')
  return data.items
}

export async function reviewActivityGuide(
  id: string,
  action: 'approve' | 'reject',
  reason = '',
): Promise<ActivityGuide> {
  const { data } = await api.post<ActivityGuide>(`/admin/activity-guide-reviews/${id}`, {
    action,
    reason,
  })
  return data
}

export async function moderateActivityGuide(
  id: string,
  action: 'unpublish' | 'republish',
  reason = '',
): Promise<ActivityGuide> {
  const { data } = await api.post<ActivityGuide>(`/admin/activity-guides/${id}/moderation`, {
    action,
    reason,
  })
  return data
}

export async function getStories(params: {
  q?: string
  version?: string
  world?: string
  mission_type?: string
  series?: string
  character?: string
} = {}): Promise<{ items: StorySummary[]; total: number; filters: StoryFilters }> {
  const { data } = await api.get('/stories', { params })
  return data
}

export async function getStory(id: string): Promise<StoryDetail> {
  const { data } = await api.get<StoryDetail>(`/stories/${id}`)
  return data
}

export async function getStoryScene(missionId: string, chunkId: string): Promise<StoryScene> {
  const { data } = await api.get<StoryScene>(`/stories/${missionId}/scenes/${chunkId}`)
  return data
}
