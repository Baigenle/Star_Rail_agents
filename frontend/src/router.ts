import { createRouter, createWebHistory } from 'vue-router'

import CharacterDetailPage from './pages/CharacterDetailPage.vue'
import CharacterLibraryPage from './pages/CharacterLibraryPage.vue'
import ChatPage from './pages/ChatPage.vue'
import ItemDetailPage from './pages/ItemDetailPage.vue'
import LightconeDetailPage from './pages/LightconeDetailPage.vue'
import RelicDetailPage from './pages/RelicDetailPage.vue'
import EntityLibraryPage from './pages/EntityLibraryPage.vue'
import LoginPage from './pages/LoginPage.vue'
import ProfilePage from './pages/ProfilePage.vue'
import CreatorLibraryPage from './pages/CreatorLibraryPage.vue'
import CreatorWorkbenchPage from './pages/CreatorWorkbenchPage.vue'
import CommunityCharacterLibraryPage from './pages/CommunityCharacterLibraryPage.vue'
import CommunityCharacterDetailPage from './pages/CommunityCharacterDetailPage.vue'
import AdminReviewsPage from './pages/AdminReviewsPage.vue'
import TeamRecommendationPage from './pages/TeamRecommendationPage.vue'
import ProfileMemoriesPage from './pages/ProfileMemoriesPage.vue'
import PlanningPage from './pages/PlanningPage.vue'
import WeeklyPlanPage from './pages/WeeklyPlanPage.vue'
import ActivityLibraryPage from './pages/ActivityLibraryPage.vue'
import ActivityDetailPage from './pages/ActivityDetailPage.vue'
import ActivityGuideReviewsPage from './pages/ActivityGuideReviewsPage.vue'
import StoryLibraryPage from './pages/StoryLibraryPage.vue'
import StoryDetailPage from './pages/StoryDetailPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'chat', component: ChatPage },
    { path: '/login', name: 'login', component: LoginPage },
    { path: '/profile', name: 'profile', component: ProfilePage, meta: { requiresAuth: true } },
    { path: '/creator', name: 'creator', component: CreatorLibraryPage, meta: { requiresAuth: true } },
    { path: '/creator/:id', name: 'creator-workbench', component: CreatorWorkbenchPage, meta: { requiresAuth: true } },
    { path: '/community/characters', name: 'community-characters', component: CommunityCharacterLibraryPage },
    { path: '/community/characters/:id', name: 'community-character-detail', component: CommunityCharacterDetailPage },
    { path: '/admin/reviews', name: 'admin-reviews', component: AdminReviewsPage, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/teams', name: 'teams', component: TeamRecommendationPage, meta: { requiresAuth: true } },
    { path: '/profile/memories', name: 'profile-memories', component: ProfileMemoriesPage, meta: { requiresAuth: true } },
    { path: '/planning', name: 'planning', component: PlanningPage, meta: { requiresAuth: true } },
    { path: '/weekly-plan', name: 'weekly-plan', component: WeeklyPlanPage, meta: { requiresAuth: true } },
    { path: '/activities', name: 'activities', component: ActivityLibraryPage },
    { path: '/activities/:id', name: 'activity-detail', component: ActivityDetailPage },
    { path: '/stories', name: 'stories', component: StoryLibraryPage },
    { path: '/stories/:id', name: 'story-detail', component: StoryDetailPage },
    { path: '/admin/activity-guide-reviews', name: 'activity-guide-reviews', component: ActivityGuideReviewsPage, meta: { requiresAuth: true, requiresAdmin: true } },
    { path: '/characters', name: 'characters', component: CharacterLibraryPage },
    { path: '/characters/:id', name: 'character-detail', component: CharacterDetailPage },
    { path: '/items/:id', name: 'item-detail', component: ItemDetailPage },
    { path: '/lightcones/:id', name: 'lightcone-detail', component: LightconeDetailPage },
    { path: '/relics/:id', name: 'relic-detail', component: RelicDetailPage },
    { path: '/:kind(lightcones|relics|items)', name: 'entity-library', component: EntityLibraryPage },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !localStorage.getItem('star_rail_access_token')) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin) {
    try {
      const user = JSON.parse(localStorage.getItem('star_rail_user') ?? 'null')
      // 前端守卫只负责避免误入；真正的管理员权限始终由后端再次校验。
      if (!user?.is_admin) return { name: 'profile' }
    } catch {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }
})
