export interface CharacterSummary {
  id: string
  name: string
  rarity: number
  path: string
  element: string
  image_url?: string
}

export interface NamedDescription {
  name: string
  description: string
  type?: string
  image_url?: string
}

export interface RelatedItem {
  id: string
  name: string
  rarity: string
  type: string
  description: string
  image_url?: string
}

export interface EntityRecommendation {
  id: string
  name: string
  kind: string
  image_url?: string
  image_status: 'official' | 'category_placeholder'
  set_type?: 'cavern' | 'planar'
  piece_count?: number
}

export interface KnowledgeEntitySummary {
  id: string
  name: string
  kind: 'characters' | 'lightcones' | 'relics' | 'items' | 'monsters'
  subtitle: string
  image_url?: string
  image_status: 'official' | 'category_placeholder'
  rarity?: number
  path?: string
  set_type?: 'cavern' | 'planar'
  piece_count?: number
}

export interface KnowledgeEntityDetail extends KnowledgeEntitySummary {
  description: string
  sections: NamedDescription[]
  related_entities: KnowledgeEntitySummary[]
  source_url?: string
  data_version?: string
}

export interface CharacterDetail extends CharacterSummary {
  description: string
  energy?: string
  stats: Record<string, string>
  skills: NamedDescription[]
  eidolons: NamedDescription[]
  related_items: RelatedItem[]
  recommended_lightcones: EntityRecommendation[]
  recommended_relics: EntityRecommendation[]
  story: string
  community_source_url?: string
  portrait_url?: string
  element_icon_url?: string
  path_icon_url?: string
  source_url: string
  data_version?: string
}

export interface ItemDetail extends RelatedItem {
  background: string
  sources: string[]
  pile_limit?: number
  source_url?: string
  related_entities: KnowledgeEntitySummary[]
}

export interface LightconeLevelStats {
  level: number
  hp: number
  attack: number
  defence: number
}

export interface LightconeMaterial extends RelatedItem {
  quantity: number
}

export interface LightconeDetail extends KnowledgeEntityDetail {
  lore_description: string
  effect_name: string
  superimposition_effects: string[]
  level_stats: LightconeLevelStats[]
  promotion_materials: Record<string, LightconeMaterial[]>
}

export interface RelicDetail extends KnowledgeEntityDetail {
  set_type: 'cavern' | 'planar'
  piece_count: number
  acquisition: string
  set_effects: NamedDescription[]
  pieces: NamedDescription[]
  community_source_url?: string
}
