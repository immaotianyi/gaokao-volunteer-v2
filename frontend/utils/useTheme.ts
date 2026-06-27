/**
 * 主题切换 composable — 暮色（深色）/ 晨光（浅色）
 * 真相源：document.documentElement.dataset.theme + localStorage
 * module-level ref 单例，多组件实例共享响应式状态
 */
import { ref } from "vue"

export type Theme = "dark" | "light"

const theme = ref<Theme>("dark")
let inited = false

function apply(t: Theme) {
  theme.value = t
  document.documentElement.setAttribute("data-theme", t)
  try { localStorage.setItem("gaokao_theme", t) } catch { /* ignore */ }
}

export function useTheme() {
  function init() {
    if (inited) return
    inited = true
    let saved: Theme | null = null
    try { saved = localStorage.getItem("gaokao_theme") as Theme | null } catch { /* ignore */ }
    // 跟随系统偏好（仅首次无保存时）
    if (saved !== "light" && saved !== "dark") {
      const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches
      saved = prefersLight ? "light" : "dark"
    }
    apply(saved)
  }

  function toggle() {
    apply(theme.value === "dark" ? "light" : "dark")
  }

  return { theme, init, toggle }
}
