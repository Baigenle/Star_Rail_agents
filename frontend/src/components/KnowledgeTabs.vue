<script setup lang="ts">
const categories = [
  { label: '角色', to: '/characters' },
  { label: '光锥', to: '/lightcones' },
  { label: '遗器', to: '/relics' },
  { label: '物品', to: '/items' },
]
</script>

<template>
  <nav class="knowledge-tabs" aria-label="游戏智库分类">
    <span>游戏智库</span>
    <router-link v-for="category in categories" :key="category.to" :to="category.to">{{ category.label }}</router-link>
  </nav>
</template>
