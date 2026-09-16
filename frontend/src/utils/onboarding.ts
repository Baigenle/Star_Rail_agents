const ONBOARDING_KEY = 'star_rail_onboarding_done'

function readDoneIds(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(ONBOARDING_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : []
  } catch {
    return []
  }
}

export function hasCompletedOnboarding(userId: string): boolean {
  return readDoneIds().includes(userId)
}

export function markOnboardingComplete(userId: string): void {
  const doneIds = readDoneIds()
  if (!doneIds.includes(userId)) doneIds.push(userId)
  localStorage.setItem(ONBOARDING_KEY, JSON.stringify(doneIds))
}
