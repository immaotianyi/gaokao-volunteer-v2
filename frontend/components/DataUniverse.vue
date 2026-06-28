<!--
  components/DataUniverse.vue — Three.js 满天繁星背景
  全屏 canvas，z-index:0 置于所有界面底层。
  4000 颗暖色星点（ShaderMaterial 逐星闪烁）+ 9 个人文图标 Sprite（毛笔字/灯笼/月亮/远山）。
  暴露 setComputeSpeed(level) 控制旋转速度与亮度。
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
let material: THREE.ShaderMaterial | null = null
let starTexture: THREE.Texture | null = null
let sprites: THREE.Sprite[] = []
let spriteTextures: THREE.Texture[] = []
let rafId = 0
const clock = new THREE.Clock()

// 速度档位：控制旋转速度与亮度倍增（聚拢改为亮度，更符合星空语义）
const SPEED_PROFILE: Record<ComputeLevel, { rotate: number; brightness: number; lerp: number }> = {
  idle:    { rotate: 0.0003, brightness: 1.0, lerp: 0.02 },
  low:     { rotate: 0.0006, brightness: 1.0, lerp: 0.03 },
  normal:  { rotate: 0.0012, brightness: 1.0, lerp: 0.04 },
  awake:   { rotate: 0.002,  brightness: 1.2, lerp: 0.04 },
  charge:  { rotate: 0.004,  brightness: 1.4, lerp: 0.05 },
  high:    { rotate: 0.007,  brightness: 1.6, lerp: 0.07 },
  surge:   { rotate: 0.01,   brightness: 1.85, lerp: 0.09 },
  focus:   { rotate: 0.005,  brightness: 1.3, lerp: 0.06 },
  release: { rotate: 0.0005, brightness: 1.0, lerp: 0.04 },
}
let currentLevel: ComputeLevel = "idle"
let targetBrightness = SPEED_PROFILE.idle.brightness
let currentBrightness = SPEED_PROFILE.idle.brightness

// ── 可访问性 + 可见性：切后台暂停 rAF，prefers-reduced-motion 降低旋转 ──
const prefersReducedMotion =
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches
let isVisible = true

// ── 星芒纹理：中心白核 + 烛光晕染 ──
function createStarTexture(): THREE.Texture {
  const size = 64
  const canvas = document.createElement("canvas")
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext("2d")!
  const cx = size / 2
  const g = ctx.createRadialGradient(cx, cx, 0, cx, cx, size / 2)
  g.addColorStop(0, "rgba(255, 255, 255, 1)")
  g.addColorStop(0.18, "rgba(255, 250, 230, 0.85)")
  g.addColorStop(0.45, "rgba(232, 185, 116, 0.3)")
  g.addColorStop(1, "rgba(232, 185, 116, 0)")
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

// ── 人文图标纹理（毛笔字 / 灯笼 / 月亮 / 远山）──
function createIconTexture(type: string): THREE.Texture {
  const size = 256
  const canvas = document.createElement("canvas")
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext("2d")!
  const cx = size / 2
  const cy = size / 2
  ctx.textAlign = "center"
  ctx.textBaseline = "middle"

  const brushFont = `bold 170px "STKaiti", "Kaiti SC", "STSong", "Songti SC", serif`

  switch (type) {
    case "福":
    case "愿":
    case "梦":
    case "志":
    case "登":
    case "科": {
      // 毛笔字 + 印章方框
      ctx.fillStyle = "rgba(232, 185, 116, 0.95)"
      ctx.font = brushFont
      ctx.fillText(type, cx, cy + 8)
      ctx.strokeStyle = "rgba(248, 113, 113, 0.55)"
      ctx.lineWidth = 5
      ctx.strokeRect(cx - 92, cy - 92, 184, 184)
      break
    }
    case "lantern": {
      // 灯笼
      ctx.fillStyle = "rgba(252, 165, 60, 0.92)"
      ctx.beginPath()
      ctx.ellipse(cx, cy, 68, 88, 0, 0, Math.PI * 2)
      ctx.fill()
      ctx.strokeStyle = "rgba(232, 185, 116, 0.5)"
      ctx.lineWidth = 2
      for (let i = -2; i <= 2; i++) {
        ctx.beginPath()
        ctx.ellipse(cx + i * 24, cy, 7, 88, 0, 0, Math.PI * 2)
        ctx.stroke()
      }
      // 上下挂绳
      ctx.strokeStyle = "rgba(252, 211, 77, 0.85)"
      ctx.lineWidth = 4
      ctx.beginPath()
      ctx.moveTo(cx, cy - 88); ctx.lineTo(cx, cy - 112)
      ctx.moveTo(cx, cy + 88); ctx.lineTo(cx, cy + 118)
      ctx.stroke()
      // 顶帽
      ctx.fillStyle = "rgba(212, 154, 78, 0.9)"
      ctx.fillRect(cx - 26, cy - 108, 52, 12)
      break
    }
    case "moon": {
      // 弯月
      ctx.fillStyle = "rgba(254, 243, 199, 0.92)"
      ctx.beginPath()
      ctx.arc(cx, cy, 78, 0, Math.PI * 2)
      ctx.fill()
      ctx.globalCompositeOperation = "destination-out"
      ctx.beginPath()
      ctx.arc(cx + 32, cy - 14, 72, 0, Math.PI * 2)
      ctx.fill()
      ctx.globalCompositeOperation = "source-over"
      // 月光晕
      const halo = ctx.createRadialGradient(cx, cy, 60, cx, cy, 120)
      halo.addColorStop(0, "rgba(254, 243, 199, 0.25)")
      halo.addColorStop(1, "rgba(254, 243, 199, 0)")
      ctx.fillStyle = halo
      ctx.fillRect(0, 0, size, size)
      break
    }
    case "mountain": {
      // 远山（两层）
      ctx.fillStyle = "rgba(212, 154, 78, 0.55)"
      ctx.beginPath()
      ctx.moveTo(24, cy + 70)
      ctx.lineTo(cx - 70, cy - 30)
      ctx.lineTo(cx - 20, cy + 10)
      ctx.lineTo(cx + 50, cy - 60)
      ctx.lineTo(cx + 100, cy - 5)
      ctx.lineTo(size - 24, cy + 70)
      ctx.closePath()
      ctx.fill()
      ctx.fillStyle = "rgba(232, 185, 116, 0.4)"
      ctx.beginPath()
      ctx.moveTo(24, cy + 90)
      ctx.lineTo(cx - 40, cy + 5)
      ctx.lineTo(cx + 20, cy + 35)
      ctx.lineTo(cx + 80, cy - 15)
      ctx.lineTo(size - 24, cy + 90)
      ctx.closePath()
      ctx.fill()
      break
    }
  }

  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

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
  const isMobile = window.innerWidth < 768
  renderer.setPixelRatio(isMobile ? 1 : Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(0x000000, 0)

  // ── 星点数量：PC 4000，移动端 2000 ──
  const COUNT = isMobile ? 2000 : 4000
  const positions = new Float32Array(COUNT * 3)
  const colors = new Float32Array(COUNT * 3)
  const sizes = new Float32Array(COUNT)
  const phases = new Float32Array(COUNT)

  // 暖色星调：暖白 / 烛光琥珀 / 淡金 / 偶尔朱砂
  const palette = [
    new THREE.Color("#fff7e6"), // 暖白
    new THREE.Color("#fef3c7"), // 淡奶黄
    new THREE.Color("#e8b974"), // 烛光琥珀
    new THREE.Color("#fcd34d"), // 淡金
    new THREE.Color("#f87171"), // 朱砂（红巨星，少量）
  ]
  const tmpColor = new THREE.Color()

  for (let i = 0; i < COUNT; i++) {
    // 球面随机分布，半径 150-720
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    const r = 150 + Math.random() * 570
    positions[i * 3]     = r * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
    positions[i * 3 + 2] = r * Math.cos(phi)

    // 颜色：大部分暖白/琥珀，少量金/朱砂
    const roll = Math.random()
    let pick: THREE.Color
    if (roll < 0.55) pick = palette[0]
    else if (roll < 0.78) pick = palette[1]
    else if (roll < 0.9) pick = palette[2]
    else if (roll < 0.97) pick = palette[3]
    else pick = palette[4]
    tmpColor.copy(pick)
    // 轻微亮度抖动
    const jitter = 0.8 + Math.random() * 0.4
    colors[i * 3]     = tmpColor.r * jitter
    colors[i * 3 + 1] = tmpColor.g * jitter
    colors[i * 3 + 2] = tmpColor.b * jitter

    // 星点大小：大部分小，少数大亮星
    sizes[i] = Math.random() < 0.08 ? 2.5 + Math.random() * 2.5 : 0.8 + Math.random() * 1.4
    phases[i] = Math.random()
  }

  geometry = new THREE.BufferGeometry()
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute("aColor", new THREE.BufferAttribute(colors, 3))
  geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1))
  geometry.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1))

  starTexture = createStarTexture()

  material = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uPixelRatio: { value: renderer.getPixelRatio() },
      uBrightness: { value: 1.0 },
      uStarTexture: { value: starTexture },
    },
    vertexShader: `
      attribute float aSize;
      attribute float aPhase;
      attribute vec3 aColor;
      uniform float uTime;
      uniform float uPixelRatio;
      uniform float uBrightness;
      varying vec3 vColor;
      varying float vTwinkle;
      void main() {
        vColor = aColor;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        // 逐星闪烁：每颗星独立相位
        float twinkle = 0.35 + 0.65 * sin(uTime * 1.6 + aPhase * 6.2831);
        vTwinkle = twinkle;
        float size = aSize * (0.7 + 0.3 * twinkle) * uBrightness;
        gl_PointSize = max(1.0, size * uPixelRatio * (260.0 / max(1.0, -mvPosition.z)));
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      uniform sampler2D uStarTexture;
      varying vec3 vColor;
      varying float vTwinkle;
      void main() {
        vec4 tex = texture2D(uStarTexture, gl_PointCoord);
        float alpha = tex.a * (0.25 + 0.75 * vTwinkle);
        if (alpha < 0.01) discard;
        // 中心更白，边缘保留星色
        vec3 col = vColor * (0.55 + 0.45 * tex.rgb);
        gl_FragColor = vec4(col, alpha);
      }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  })

  points = new THREE.Points(geometry, material)
  scene.add(points)

  // ── 人文图标 Sprite 层 ──
  const iconTypes = ["福", "愿", "梦", "志", "登", "科", "lantern", "moon", "mountain"]
  iconTypes.forEach((type) => {
    const tex = createIconTexture(type)
    spriteTextures.push(tex)
    const mat = new THREE.SpriteMaterial({
      map: tex,
      transparent: true,
      opacity: 0.45,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    })
    const sprite = new THREE.Sprite(mat)
    // 随机散布在半径 320-560 的球面上
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    const r = 320 + Math.random() * 240
    sprite.position.set(
      r * Math.sin(phi) * Math.cos(theta),
      r * Math.sin(phi) * Math.sin(theta),
      r * Math.cos(phi),
    )
    const scale = 34 + Math.random() * 26
    sprite.scale.set(scale, scale, 1)
    sprite.userData.baseOpacity = 0.35 + Math.random() * 0.25
    sprite.userData.phase = Math.random() * Math.PI * 2
    sprite.userData.driftBaseY = sprite.position.y
    scene!.add(sprite)
    sprites.push(sprite)
  })
}

// ── 动画循环 ────────────────────────────────────────────
function animate() {
  rafId = requestAnimationFrame(animate)
  // 切到后台时不渲染，节省移动端电量
  if (!isVisible || !points || !geometry || !renderer || !camera || !scene || !material) return

  const t = clock.getElapsedTime()
  const profile = SPEED_PROFILE[currentLevel]
  // prefers-reduced-motion: 大幅降低旋转速度，避免动效刺激
  const rotateFactor = prefersReducedMotion ? 0.15 : 1
  targetBrightness = profile.brightness
  currentBrightness += (targetBrightness - currentBrightness) * profile.lerp

  // 旋转（双轴，增强立体感）
  points.rotation.y += profile.rotate * rotateFactor
  points.rotation.x += profile.rotate * 0.35 * rotateFactor

  // 更新 shader uniform
  material.uniforms.uTime.value = t
  material.uniforms.uBrightness.value = currentBrightness

  // 图标 Sprite 呼吸 + 缓慢漂浮
  for (const s of sprites) {
    const phase = s.userData.phase as number
    const base = s.userData.baseOpacity as number
    const mat = s.material as THREE.SpriteMaterial
    mat.opacity = base * (0.65 + 0.35 * Math.sin(t * 0.7 + phase)) * currentBrightness
    s.position.y = (s.userData.driftBaseY as number) + Math.sin(t * 0.25 + phase) * 6
    // 图标整体也跟随星点缓慢旋转
    s.rotation.z += profile.rotate * 0.5 * rotateFactor
  }

  renderer.render(scene, camera)
}

// ── 标签页可见性：hidden 暂停 rAF，visible 恢复 ──
function handleVisibility() {
  if (document.hidden) {
    isVisible = false
    if (rafId) {
      cancelAnimationFrame(rafId)
      rafId = 0
    }
  } else if (!isVisible) {
    isVisible = true
    if (!rafId) animate()
  }
}

// ── 窗口尺寸响应 ────────────────────────────────────────
function onResize() {
  if (!camera || !renderer || !material) return
  const w = window.innerWidth
  const h = window.innerHeight
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
  material.uniforms.uPixelRatio.value = renderer.getPixelRatio()
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
  document.addEventListener("visibilitychange", handleVisibility)
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize)
  document.removeEventListener("visibilitychange", handleVisibility)
  cancelAnimationFrame(rafId)

  if (geometry) {
    geometry.dispose()
    geometry = null
  }
  if (material) {
    material.dispose()
    material = null
  }
  if (starTexture) {
    starTexture.dispose()
    starTexture = null
  }
  for (const tex of spriteTextures) tex.dispose()
  spriteTextures = []
  for (const s of sprites) {
    ;(s.material as THREE.SpriteMaterial).dispose()
  }
  sprites = []
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
  opacity: 0.55;
  pointer-events: none;
}
</style>
