import { createRouter, createWebHashHistory } from "vue-router";

const router = createRouter({
  // 使用 hash 模式，避免 nginx 未配置 SPA fallback 时刷新 404 / 主页消失
  history: createWebHashHistory(),
  routes: [
    {
      path: "/",
      component: () => import("./pages/landing/landing.vue"),
    },
    {
      path: "/workbench",
      component: () => import("./pages/index/index.vue"),
    },
    {
      path: "/pages/index/index",
      redirect: "/workbench",
    },
    {
      path: "/pages/profile/profile",
      component: () => import("./pages/profile/profile.vue"),
    },
  ],
});

export default router;
