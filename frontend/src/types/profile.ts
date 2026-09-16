export interface UserCharacter {
  character_id: string
  name: string
  rarity: number
  path: string
  element: string
  image_url?: string | null
  level: number
  eidolon: number
  is_favorite: boolean
  is_built: boolean
  created_at: string
  updated_at: string
}

export interface CharacterPool {
  items: UserCharacter[]
  total: number
  favorites: number
}
