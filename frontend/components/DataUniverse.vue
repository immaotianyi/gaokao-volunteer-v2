<!--
  components/DataUniverse.vue — Three.js 粒子宇宙背景
  全屏 canvas，z-index:0 置于所有界面底层，低透明度防止喧宾夺主。
  5000 粒子分布于双螺旋空间，颜色混合 #38bdf8 / #818cf8。
  暴露 setComputeSpeed(level) 控制旋转速度与聚拢效果。
-->
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue"
import * as THREE from "three"

type ComputeLevel = "idle" | "low" | "normal" | "high" | "awake" | "charge" | "surge" | "focus" | "release"

const canvasRef = ref<HTMLCanvasElement | null>(null)

let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let points: THREE.Points | null = null
let geometry: THREE.BufferGeometry | null = null
let material: THREE.PointsMaterial | null = null
let rafId = 0

// 粒子原始位置（用于 high 模式聚拢后恢复）
let basePositions: Float32Array | null = null

// 速度档位参数
const SPEED_PROFILE: Record<ComputeLevel, { rotate: number; gather: number; lerp: number }> = {
  idle:    { rotate: 0.0004, gather: 1.0,  lerp: 0.02 },  // 极慢漂浮（初始）
  low:     { rotate: 0.0008, gather: 1.0,  lerp: 0.03 },  // 低速（扫描结束后恢复）
  normal:  { rotate: 0.0015, gather: 1.0,  lerp: 0.04 },  // 常规
  awake:   { rotate: 0.0025, gather: 0.88, lerp: 0.04 },  // 唤醒：粒子开始缓慢聚拢
  charge:  { rotate: 0.005,  gather: 0.6,  lerp: 0.05 },  // 蓄力：加速旋转 + 持续聚拢
  high:    { rotate: 0.009,  gather: 0.3,  lerp: 0.07 },  // 高速：快速自转 + 紧聚拢
  surge:   { rotate: 0.014,  gather: 0.15, lerp: 0.09 },  // 涌流：峰值算力
  focus:   { rotate: 0.007,  gather: 0.4,  lerp: 0.06 },  // 聚焦：逐条检索时的节奏感
  release: { rotate: 0.0006, gather: 1.0,  lerp: 0.04 },  // 释放：缓缓散开恢复
}
let currentLevel: ComputeLevel = "idle"
let targetGather = SPEED_PROFILE.idle.gather
let currentGather = SPEED_PROFILE.idle.gather

// ── 初始化场景 ──────────────────────────────────────────
function initScene() {
  const canvas = canvasRef.value
  if (!canvas) return

  const w = window.innerWidth
  const h = window.innerHeight

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(60, w / h, 0.1, 2000)
  camera.position.z = 320

  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: false })
  renderer.setSize(w, h)
  // 移动端降低 pixelRatio 防止发烫掉帧
  const isMobile = window.innerWidth < 768
  renderer.setPixelRatio(isMobile ? 1 : Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(0x000000, 0)

  // ── 粒子数量：PC 5000，移动端减半 2500 ──
  const COUNT = isMobile ? 2500 : 5000
  const positions = new Float32Array(COUNT * 3)
  const colors = new Float32Array(COUNT * 3)

  // 项目主色
  const colorA = new THREE.Color("#38bdf8") // 赛博蓝
  const colorB = new THREE.Color("#818cf8") // 靛紫
  const tmpColor = new THREE.Color()

  for (let i = 0; i < COUNT; i++) {
    const t = i / COUNT
    // 双螺旋：两条螺旋臂，半径随高度收缩
    const arm = i % 2 === 0 ? 0 : Math.PI
    const angle = t * Math.PI * 14 + arm
    const radius = 40 + Math.sin(t * Math.PI) * 160 + (Math.random() - 0.5) * 30
    const height = (t - 0.5) * 420 + (Math.random() - 0.5) * 40

    const x = Math.cos(angle) * radius
    const y = height
    const z = Math.sin(angle) * radius

    positions[i * 3]     = x
    positions[i * 3 + 1] = y
    positions[i * 3 + 2] = z

    // 颜色混合：按螺旋臂与高度混合 A/B
    const mix = (Math.sin(t * Math.PI * 2 + arm) + 1) / 2
    tmpColor.copy(colorA).lerp(colorB, mix)
    colors[i * 3]     = tmpColor.r
    colors[i * 3 + 1] = tmpColor.g
    colors[i * 3 + 2] = tmpColor.b
  }

  basePositions = new Float32Array(positions)

  geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3))

  material = new THREE.PointsMaterial({
    size: 2.2,
    vertexColors: true,
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    sizeAttenuation: true,
  })

  points = new THREE.Points(geometry, material)
  scene.add(points)
}

// ── 动画循环 ────────────────────────────────────────────
function animate() {
  rafId = requestAnimationFrame(animate)
  if (!points || !geometry || !renderer || !camera || !scene) return

  const profile = SPEED_PROFILE[currentLevel]
  targetGather = profile.gather
  currentGather += (targetGather - currentGather) * profile.lerp

  // 旋转（双轴，增强立体感）
  points.rotation.y += profile.rotate
  points.rotation.x += profile.rotate * 0.35

  // 聚拢/恢复：将粒子位置向中心缩放
  if (basePositions) {
    const posAttr = geometry.getAttribute("position") as THREE.BufferAttribute
    const arr = posAttr.array as Float32Array
    for (let i = 0; i < arr.length; i++) {
      arr[i] = (basePositions[i] ?? 0) * currentGather
    }
    posAttr.needsUpdate = true
  }

  renderer.render(scene, camera)
}

// ── 窗口尺寸响应 ────────────────────────────────────────
function onResize() {
  if (!camera || !renderer) return
  const w = window.innerWidth
  const h = window.innerHeight
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
}

// ── 暴露控制接口 ────────────────────────────────────────
function setComputeSpeed(level: ComputeLevel) {
  currentLevel = level
}

defineExpose({ setComputeSpeed })

onMounted(() => {
  initScene()
  animate()
  window.addEventListener("resize", onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize)
  cancelAnimationFrame(rafId)

  if (geometry) {
    geometry.dispose()
    geometry = null
  }
  if (material) {
    material.dispose()
    material = null
  }
  if (renderer) {
    renderer.dispose()
    renderer = null
  }
  if (scene) {
    scene.clear()
    scene = null
  }
  points = null
  camera = null
  basePositions = null
})
</script>

<template>
  <canvas ref="canvasRef" class="data-universe-canvas" />
</template>

<style scoped>
.data-universe-canvas {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  opacity: 0.22;
  pointer-events: none;
}
</style>
