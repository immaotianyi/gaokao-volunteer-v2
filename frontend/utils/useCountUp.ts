/**
 * useCountUp — 手写数字滚动动画（老虎机机制）
 *
 * 用法:
 *   const { display, rolling, start } = useCountUp()
 *   start(542, 800)  // 从 0 滚到 542，耗时 800ms
 *   // display.value 即时变化，rolling.value 标记是否在滚动中
 */
import { ref, onBeforeUnmount } from "vue"

export function useCountUp() {
  const display = ref(0)
  const rolling = ref(false)
  let rafId = 0
  let startTs = 0
  let fromVal = 0
  let toVal = 0
  let duration = 0

  function easeOutExpo(t: number): number {
    return t === 1 ? 1 : 1 - Math.pow(2, -10 * t)
  }

  function tick() {
    const elapsed = Date.now() - startTs
    const t = Math.min(1, elapsed / duration)
    const eased = easeOutExpo(t)
    display.value = Math.round(fromVal + (toVal - fromVal) * eased)
    if (t < 1) {
      rafId = requestAnimationFrame(tick)
    } else {
      display.value = toVal
      rolling.value = false
    }
  }

  /** 从当前值滚动到 target，耗时 ms */
  function start(target: number, ms = 800) {
    cancelAnimationFrame(rafId)
    fromVal = display.value
    toVal = target
    duration = ms
    rolling.value = true
    startTs = Date.now()
    rafId = requestAnimationFrame(tick)
  }

  /** 重置为 0 */
  function reset() {
    cancelAnimationFrame(rafId)
    display.value = 0
    rolling.value = false
  }

  onBeforeUnmount(() => { cancelAnimationFrame(rafId) })

  return { display, rolling, start, reset }
}
