<script setup lang="ts">
import { onMounted } from "vue";
import { useProfileStore } from "./stores/profile";

onMounted(() => {
  const store = useProfileStore();
  // 1. 先从本地缓存恢复
  store.loadFromCache();
  // 2. 异步尝试从后端同步（静默失败）
  store.loadFromBackend();
});
</script>

<template>
  <router-view />
</template>

<style>
@import "./static/index.css";
</style>
