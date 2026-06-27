import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import router from "./router";
import { useTheme } from "./utils/useTheme";

// 挂载前初始化主题，避免首屏闪烁
useTheme().init();

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");
