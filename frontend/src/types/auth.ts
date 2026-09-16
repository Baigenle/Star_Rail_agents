export interface UserProfile {
  id: string
  username: string
  email: string
  display_name: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: UserProfile
}
