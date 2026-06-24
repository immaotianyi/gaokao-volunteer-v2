<!--
  components/ArmorParticles.vue — 盔甲人 GLB → 粒子点云
  所有可调参数集中在顶部 CONFIG，直接改数值即可调试。
-->
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue"
import * as THREE from "three"
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js"

const containerRef = ref<HTMLDivElement | null>(null)

let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let points: THREE.Points | null = null
let originalModel: THREE.Group | null = null  // 保存原始模型引用
let rafId = 0

// ═══════════════════════════════════════════════════
//  🎛 所有可调参数（直接改数值即可调试）
// ═══════════════════════════════════════════════════
const CONFIG = {
  // ── 顶点 ──
  sampleRate: 0.0015,     // 采样率（0~1），越小越稀疏。0.0015=0.15%
  maxVertices: 200_000,   // 顶点上限，超过则截断

  // ── 粒子外观 ──
  enableParticles: false,     // 是否启用粒子效果
  pointSize: 0.066,       // 粒子大小（已放大 300%：0.022→0.066）
  pointOpacity: 0.85,     // 透明度（0~1）

  // ── 呼吸动画 ──
  breathSpeed: 1.2,       // 呼吸频率，越大越快
  breathAmplitude: 0.2,   // 呼吸幅度，0=无呼吸，0.2=±20%

  // ── 旋转 ──
  rotateSpeed: 0,         // Y 轴自转速度（0=停止旋转）

  // ── 相机（正面顺时针旋转 90° = 侧面视角）──
  cameraFov: 50,          // 视场角
  cameraX: 1.17, cameraY: 0.4, cameraZ: 0,  // 相机距离缩小至 1/3（3.5→1.17）
  lookAtX: 0, lookAtY: 0.5, lookAtZ: 0,     // 注视点不变

  // ── 点云缩放 ──
  modelScale: 1.5,        // 点云整体缩放倍数（150%，缩小一倍）

  // ── 原始模型显示 ──
  showOriginalModel: true,  // 是否显示原始模型（半透明）
  originalModelOpacity: 1.0, // 原始模型透明度（0~1），1.0 = 100% 不透明

  // ── 点云位置偏移 ──
  offsetY: 0.25,          // 点云 Y 轴偏移（上移到 0.25）

  // ── 场景背景 ──
  bgColor: "#1a1a2e",     // 背景色（CSS 色值）

  // ── 模型路径 ──
  modelPath: "/models/armor.glb",
} as const

// ── 提取顶点 + 上限截断 ──
function extractVertices(model: THREE.Group): Float32Array {
  const allVerts: number[] = []
  const { sampleRate, maxVertices } = CONFIG

  model.traverse((child) => {
    if (!(child instanceof THREE.Mesh) || !child.geometry) return
    const geom = child.geometry
    if (!geom.attributes.position) return

    const posAttr = geom.attributes.position
    const verts = posAttr.array as Float32Array

    if (geom.index) {
      const idxArr = geom.index.array
      for (let i = 0; i < idxArr.length; i++) {
        if (allVerts.length >= maxVertices * 3) break
        if (Math.random() > sampleRate) continue
        const vi = idxArr[i] * 3
        allVerts.push(verts[vi], verts[vi + 1], verts[vi + 2])
      }
    } else {
      for (let i = 0; i < verts.length; i += 3) {
        if (allVerts.length >= maxVertices * 3) break
        if (Math.random() > sampleRate) continue
        allVerts.push(verts[i], verts[i + 1], verts[i + 2])
      }
    }
  })

  if (allVerts.length > maxVertices * 3) {
    allVerts.length = maxVertices * 3
  }

  return new Float32Array(allVerts)
}

// ── 递归 dispose 模型所有 Mesh（防止内存泄漏） ──
function disposeModel(model: THREE.Group) {
  model.traverse((child) => {
    if (child instanceof THREE.Mesh) {
      child.geometry?.dispose()
      if (Array.isArray(child.material)) {
        child.material.forEach(m => m.dispose())
      } else {
        child.material?.dispose()
      }
    }
  })
}

// ── 初始化场景 ──
function initScene() {
  const container = containerRef.value
  if (!container) return

  const w = container.clientWidth
  const h = container.clientHeight

  scene = new THREE.Scene()
  scene.background = new THREE.Color(CONFIG.bgColor)

  // ── 添加光照（提高亮度）──
  // 环境光：整体基础照明（提高至 1.0）
  const ambientLight = new THREE.AmbientLight(0xffffff, 1.0)
  scene.add(ambientLight)

  // 主光源：从正面右上方照射（提高至 1.2）
  const mainLight = new THREE.DirectionalLight(0xffffff, 1.2)
  mainLight.position.set(5, 10, 7)
  scene.add(mainLight)

  // 补光：从左侧照射，减少阴影（提高至 0.6）
  const fillLight = new THREE.DirectionalLight(0xffffff, 0.6)
  fillLight.position.set(-5, 5, 3)
  scene.add(fillLight)

  camera = new THREE.PerspectiveCamera(CONFIG.cameraFov, w / h, 0.1, 1000)
  camera.position.set(CONFIG.cameraX, CONFIG.cameraY, CONFIG.cameraZ)
  camera.lookAt(CONFIG.lookAtX, CONFIG.lookAtY, CONFIG.lookAtZ)

  // 像素比限制：移动端 1，高分屏不超过 2
  const isMobile = window.innerWidth < 768
  const maxDpr = isMobile ? 1 : 2
  renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, maxDpr))
  container.appendChild(renderer.domElement)
}

// ── 加载模型 → 提取顶点 → 添加半透明原始模型 + 粒子点云 ──
function loadModel() {
  // 模型放在 /public/models/ 下，Vite 不会打包，通过 HTTP 请求加载
  const loader = new GLTFLoader()
  loader.load(
    CONFIG.modelPath,
    (gltf) => {
      const model = gltf.scene

      // 1. 提取顶点
      const vertices = extractVertices(model)
      const vertexCount = vertices.length / 3
      console.log(`[ArmorParticles] 提取 ${vertexCount.toLocaleString()} 个顶点${vertexCount >= CONFIG.maxVertices ? '（已达上限）' : ''}`)

      // 2. 如果启用，添加半透明原始模型
      if (CONFIG.showOriginalModel) {
        originalModel = model

        // 设置材质透明度
        model.traverse((child) => {
          if (child instanceof THREE.Mesh && child.material) {
            if (Array.isArray(child.material)) {
              child.material.forEach((mat) => {
                if (CONFIG.originalModelOpacity < 1.0) {
                  mat.transparent = true
                  mat.depthWrite = false
                } else {
                  // 100% 不透明时，不使用透明渲染（避免黑影）
                  mat.transparent = false
                  mat.depthWrite = true
                }
                mat.opacity = CONFIG.originalModelOpacity
              })
            } else {
              if (CONFIG.originalModelOpacity < 1.0) {
                child.material.transparent = true
                child.material.depthWrite = false
              } else {
                // 100% 不透明时，不使用透明渲染（避免黑影）
                child.material.transparent = false
                child.material.depthWrite = true
              }
              child.material.opacity = CONFIG.originalModelOpacity
            }
          }
        })

        model.position.y = CONFIG.offsetY
        model.scale.set(CONFIG.modelScale, CONFIG.modelScale, CONFIG.modelScale)
        scene?.add(model)
        console.log(`[ArmorParticles] 原始模型已添加（透明度 ${CONFIG.originalModelOpacity * 100}%）`)
      } else {
        // 如果不需要显示原始模型，则 dispose 释放内存
        disposeModel(model)
      }

      if (vertices.length === 0) {
        console.warn("[ArmorParticles] 模型中没有找到顶点数据")
        return
      }

      // 3. 如果启用，生成粒子点云
      if (CONFIG.enableParticles) {
        const geom = new THREE.BufferGeometry()
        geom.setAttribute("position", new THREE.BufferAttribute(vertices, 3))

        const mat = new THREE.PointsMaterial({
          color: 0x888888,       // 调暗 50%（从白色 #ffffff 改为灰色 #888888）
          size: CONFIG.pointSize,
          sizeAttenuation: true,
          blending: THREE.NormalBlending,
          depthWrite: true,
          transparent: true,
          opacity: CONFIG.pointOpacity,
        })

        points = new THREE.Points(geom, mat)
        points.position.y = CONFIG.offsetY
        points.scale.set(CONFIG.modelScale, CONFIG.modelScale, CONFIG.modelScale)
        scene?.add(points)

        console.log("[ArmorParticles] 粒子点云渲染就绪")
      } else {
        console.log("[ArmorParticles] 粒子效果已禁用")
      }
    },
    (progress) => {
      if (progress.total > 0) {
        const pct = Math.round((progress.loaded / progress.total) * 100)
        console.log(`[ArmorParticles] 加载中... ${pct}%`)
      }
    },
    (error) => {
      console.error("[ArmorParticles] 模型加载失败:", error)
    },
  )
}

// ── 动画循环 ──
function animate() {
  rafId = requestAnimationFrame(animate)

  // 只有当粒子存在时才更新粒子动画
  if (points && CONFIG.enableParticles) {
    points.rotation.y += CONFIG.rotateSpeed

    const t = performance.now() * 0.001
    const breath = 1 + Math.sin(t * CONFIG.breathSpeed) * CONFIG.breathAmplitude
    ;(points.material as THREE.PointsMaterial).size = CONFIG.pointSize * breath
  }

  if (renderer && camera && scene) {
    renderer.render(scene, camera)
  }
}

// ── 窗口响应 ──
function onResize() {
  const container = containerRef.value
  if (!container || !camera || !renderer) return
  const w = container.clientWidth
  const h = container.clientHeight
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
}

onMounted(() => {
  initScene()
  loadModel()
  animate()
  window.addEventListener("resize", onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize)
  cancelAnimationFrame(rafId)

  // 清理粒子点云
  if (points) {
    points.geometry.dispose()
    ;(points.material as THREE.Material).dispose()
    scene?.remove(points)
    points = null
  }

  // 清理原始模型
  if (originalModel) {
    disposeModel(originalModel)
    scene?.remove(originalModel)
    originalModel = null
  }

  if (renderer) {
    renderer.dispose()
    const dom = renderer.domElement
    if (dom.parentNode) dom.parentNode.removeChild(dom)
    renderer = null
  }
  scene = null
  camera = null
})
</script>

<template>
  <div ref="containerRef" class="armor-canvas" />
</template>

<style scoped>
.armor-canvas {
  width: 100%;
  height: 100%;
  min-height: 500px;
}
</style>
