import axios from 'axios'
import { defineStore } from 'pinia'

import { getCurrentUser, loginUser, registerUser } from '../services/api'
import type { UserProfile } from '../types/auth'

const TOKEN_KEY = 'star_rail_access_token'
const USER_KEY = 'star_rail_user'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) ?? '',
    user: JSON.parse(localStorage.getItem(USER_KEY) ?? 'null') as UserProfile | null,
    loading: false,
  }),
  getters: {
    isAuthenticated: (state) => Boolean(state.token && state.user),
  },
  actions: {
    save(token: string, user: UserProfile) {
      this.token = token
      this.user = user
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
    },
    async login(account: string, password: string) {
      this.loading = true
      try {
        const result = await loginUser({ account, password })
        this.save(result.access_token, result.user)
      } finally { this.loading = false }
    },
    async register(username: string, email: string, password: string, displayName: string) {
      this.loading = true
      try {
        const result = await registerUser({ username, email, password, display_name: displayName })
        this.save(result.access_token, result.user)
      } finally { this.loading = false }
    },
    async refresh() {
      if (!this.token) return
      try {
        const user = await getCurrentUser()
        this.save(this.token, user)
      } catch {
        this.logout()
      }
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
    errorMessage(error: unknown): string {
      if (axios.isAxiosError(error)) return String(error.response?.data?.detail ?? '请求失败，请稍后重试。')
      return '请求失败，请稍后重试。'
    },
  },
})
