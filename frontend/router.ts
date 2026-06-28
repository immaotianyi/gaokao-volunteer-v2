import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  // history 模式：nginx 已配置 try_files $uri $uri/ /index.html; SPA fallback
  history: createWebHistory(),
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
      path: "/profile",
      redirect: "/pages/profile/profile",
    },
    {
      path: "/pages/profile/profile",
      component: () => import("./pages/profile/profile.vue"),
    },
    // 404 兜底：未匹配路径重定向到首页
    {
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
});

export default router;
