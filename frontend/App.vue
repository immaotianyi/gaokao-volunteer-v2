<script setup lang="ts">
import { onMounted, onErrorCaptured, ref } from "vue";
import { useProfileStore } from "./stores/profile";

onMounted(() => {
  const store = useProfileStore();
  // 1. 先从本地缓存恢复
  store.loadFromCache();
  // 2. 异步尝试从后端同步（静默失败）
  store.loadFromBackend();
});

// ── 懒加载 chunk 失败兜底（弱网 / 部署更新后旧 hash 失效）──
const chunkError = ref(false);
onErrorCaptured((err) => {
  if (
    err instanceof Error &&
    /Loading chunk|Failed to fetch dynamically imported module|chunk \S+ failed|Importing a module script failed/i.test(
      err.message,
    )
  ) {
    chunkError.value = true;
    return false; // 阻止继续冒泡
  }
  return true;
});

function reloadPage() {
  if (typeof window !== "undefined") window.location.reload();
}
</script>

<template>
  <div v-if="chunkError" class="chunk-error">
    <div class="chunk-error-card">
      <div class="chunk-error-icon">⚠</div>
      <h3 class="chunk-error-title">页面加载失败</h3>
      <p class="chunk-error-desc">可能是网络波动，或系统已更新。刷新一次即可恢复。</p>
      <button class="chunk-error-btn" @click="reloadPage">重新加载</button>
    </div>
  </div>
  <router-view v-else v-slot="{ Component }">
    <Transition name="page-fade" mode="out-in">
      <Suspense>
        <component :is="Component" />
        <template #fallback>
          <div class="page-fallback">
            <div class="page-fallback-ring" />
            <span class="page-fallback-text">正在展开卷轴...</span>
          </div>
        </template>
      </Suspense>
    </Transition>
  </router-view>
</template>

<style>
@import "./static/index.css";

/* ── 路由切换过渡（与秉烛研卷主题协调）── */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.28s ease, transform 0.28s ease;
}
.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ── Suspense fallback 加载态 ── */
.page-fallback {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  background: #07101c;
  z-index: 50;
}
.page-fallback-ring {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2px solid rgba(232, 185, 116, 0.18);
  border-top-color: #e8b974;
  animation: page-fallback-spin 0.9s linear infinite;
}
@keyframes page-fallback-spin {
  to {
    transform: rotate(360deg);
  }
}
.page-fallback-text {
  font-size: 13px;
  color: #f4d8a8;
  letter-spacing: 0.15em;
}

/* ── chunk 加载失败兜底 ── */
.chunk-error {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #07101c;
  z-index: 9999;
  padding: 24px;
}
.chunk-error-card {
  max-width: 320px;
  text-align: center;
  padding: 32px 24px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(232, 185, 116, 0.2);
  border-radius: 16px;
}
.chunk-error-icon {
  font-size: 32px;
  color: #fbbf24;
  margin-bottom: 12px;
}
.chunk-error-title {
  font-size: 17px;
  font-weight: 700;
  color: #f4d8a8;
  margin: 0 0 8px;
}
.chunk-error-desc {
  font-size: 13px;
  color: #94a3b8;
  line-height: 1.6;
  margin: 0 0 20px;
}
.chunk-error-btn {
  padding: 10px 28px;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 700;
  background: linear-gradient(135deg, #e8b974, #d49a4e);
  color: #fff;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}
.chunk-error-btn:hover {
  box-shadow: 0 6px 20px rgba(232, 185, 116, 0.35);
  transform: translateY(-1px);
}
</style>
