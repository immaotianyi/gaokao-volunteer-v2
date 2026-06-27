<!--
  components/ThemeToggle.vue — 暮色/晨光主题切换
  太阳/月亮图标按钮，点击切换深浅色
-->
<script setup lang="ts">
import { useTheme } from "../utils/useTheme"
import Icon from "./Icon.vue"

const { theme, toggle } = useTheme()
</script>

<template>
  <div class="theme-toggle" :title="theme === 'dark' ? '切换到晨光（浅色）' : '切换到暮色（深色）'" @click="toggle">
    <Transition name="theme-swap" mode="out-in">
      <Icon v-if="theme === 'dark'" key="moon" name="moon" :size="14" />
      <Icon v-else key="sun" name="sun" :size="14" />
    </Transition>
  </div>
</template>

<style scoped>
.theme-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.32, 0.72, 0, 1);
  flex-shrink: 0;
}
.theme-toggle:hover {
  background: rgba(232, 185, 116, 0.12);
  border-color: rgba(232, 185, 116, 0.3);
  color: var(--accent);
  transform: translateY(-1px);
}
.theme-toggle:active { transform: translateY(0); }

.theme-swap-enter-active, .theme-swap-leave-active { transition: all 0.2s ease; }
.theme-swap-enter-from { opacity: 0; transform: rotate(-90deg) scale(0.6); }
.theme-swap-leave-to { opacity: 0; transform: rotate(90deg) scale(0.6); }
</style>
