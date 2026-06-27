<!--
  components/Icon.vue — 统一高级质感 SVG 图标库
  纯 stroke 线性图标，currentcolor 继承，配合项目赛博色调
  用法: <Icon name="shield" :size="28" />
-->
<script setup lang="ts">
const props = withDefaults(defineProps<{
  name: string
  size?: number
}>(), { size: 24 })

// 所有图标统一 viewBox="0 0 24 24", stroke-width=1.5, 无 fill
const ICONS: Record<string, string> = {
  // 盾牌（探雷器/防护）
  shield: `<path d="M12 2L4 5v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V5l-8-3z"/><path d="M9 12l2 2 4-4"/>`,
  // 雷达（捡漏雷达/扫描）
  radar: `<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/><line x1="12" y1="12" x2="20" y2="6"/>`,
  // 钻石（S级捡漏预警）
  diamond: `<path d="M6 3h12l3 6-9 12L3 9l3-6z"/><path d="M3 9h18"/><path d="M9 3l-3 6 6 12 6-12-3-6"/>`,
  // 火焰（热度/评分）
  flame: `<path d="M12 2c1 3 4 5 4 9a4 4 0 0 1-8 0c0-2 1-3 2-4-2 0-4 2-4 5a6 6 0 0 0 12 0c0-6-4-8-6-10z"/>`,
  // 返回箭头
  arrowLeft: `<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>`,
  // 锁
  lock: `<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>`,
  // 勾选
  check: `<polyline points="20 6 9 17 4 12"/>`,
  // 闪电（算力/引擎）
  bolt: `<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>`,
  // 目标/锁定（狙击镜十字）
  target: `<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="1" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="23" y2="12"/>`,
  // 数据库
  database: `<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.5 3.5 3 8 3s8-1.5 8-3V5"/><path d="M4 11v6c0 1.5 3.5 3 8 3s8-1.5 8-3v-6"/>`,
  // 用户/我的
  user: `<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-7 8-7s8 3 8 7"/>`,
  // 箭头右（开始/进入）
  arrowRight: `<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>`,
  // 趋势上升（捡漏机会）
  trending: `<polyline points="3 17 9 11 13 15 21 7"/><polyline points="14 7 21 7 21 14"/>`,
  // 警告三角
  alert: `<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>`,
  // 硬币/支付
  coin: `<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><text x="12" y="16" text-anchor="middle" font-size="9" fill="currentColor" stroke="none" font-weight="bold">¥</text>`,
  // 关闭
  close: `<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>`,

  // ── 东方人文风图标 ──
  // 卷轴（研卷/章程）
  scroll: `<ellipse cx="12" cy="4" rx="5" ry="1.5"/><path d="M7 4v16"/><path d="M17 4v16"/><ellipse cx="12" cy="20" rx="5" ry="1.5"/><line x1="9" y1="9" x2="15" y2="9"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="15" x2="13" y2="15"/>`,
  // 印章（落款/认证）
  seal: `<rect x="6" y="8" width="12" height="12" rx="1"/><line x1="9" y1="11" x2="15" y2="11"/><line x1="9" y1="14" x2="15" y2="14"/><line x1="9" y1="17" x2="15" y2="17"/><path d="M10 8V5h4v3"/>`,
  // 烛灯（陪伴/秉烛）
  candle: `<path d="M12 3c-1.2 1.5-1.8 2.5-1.8 3.5a1.8 1.8 0 0 0 3.6 0c0-1-0.6-2-1.8-3.5z"/><line x1="12" y1="7" x2="12" y2="9"/><path d="M9 9h6v9a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1z"/><line x1="8" y1="19" x2="16" y2="19"/>`,
  // 毛笔（书写/研判）
  brush: `<path d="M4 20c2-1 4-3 5-5"/><path d="M9 15l8-8"/><path d="M17 7l3-3"/><line x1="9" y1="15" x2="11" y2="17"/>`,
  // 远山（意境/陪衬）
  mountain: `<path d="M3 19l5-9 4 5 3-6 6 10z"/><path d="M3 19h18"/><circle cx="17" cy="6" r="1.5"/>`,
  // 灯笼（暖光/指引）
  lantern: `<line x1="12" y1="2" x2="12" y2="4"/><path d="M8 4h8"/><path d="M8 4c-2 2-2 10 0 12"/><path d="M16 4c2 2 2 10 0 12"/><path d="M8 16h8"/><line x1="12" y1="16" x2="12" y2="20"/><path d="M10 20h4"/>`,
  // 书签（标记/收藏）
  bookmark: `<path d="M6 3h12v18l-6-4-6 4z"/>`,
  // 卷宗/书册（档案）
  book: `<path d="M4 4h7a2 2 0 0 1 2 2v14a1 1 0 0 0-1-1H4z"/><path d="M20 4h-7a2 2 0 0 0-2 2v14a1 1 0 0 1 1-1h8z"/>`,
  // 太阳/晨光（希望/新开始）
  sun: `<circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="22"/><line x1="2" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="22" y2="12"/><line x1="5" y1="5" x2="6.5" y2="6.5"/><line x1="17.5" y1="17.5" x2="19" y2="19"/><line x1="5" y1="19" x2="6.5" y2="17.5"/><line x1="17.5" y1="6.5" x2="19" y2="5"/>`,
  moon: `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>`,
}
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    v-html="ICONS[name] || ''"
  />
</template>
