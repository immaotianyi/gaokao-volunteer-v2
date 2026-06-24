<!--
  pages/landing/landing.vue — 产品主页（宣传+引导）
  结构：导航栏 → Hero 痛点共鸣 → 数据权威 → 三大功能 → 使用流程 → 真实案例 → FAQ → CTA → Footer
-->
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue"
import { useRouter } from "vue-router"
import { useProfileStore } from "../../stores/profile"
import Icon from "../../components/Icon.vue"

const router = useRouter()
const profileStore = useProfileStore()

// 进入工作台——未完善档案时也跳转，工作台会自动弹出引导
function goToWorkbench() {
  router.push('/workbench')
}

// 锚点滚动（hash路由模式下 <a href="#xxx"> 会被当作路由，需手动处理）
function scrollToSection(id: string) {
  const el = document.getElementById(id)
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" })
}

// ── 滚动监听（导航栏背景变化）──
const scrolled = ref(false)
function onScroll() { scrolled.value = window.scrollY > 40 }
onMounted(() => window.addEventListener("scroll", onScroll))
onBeforeUnmount(() => {
  window.removeEventListener("scroll", onScroll)
  window.removeEventListener("scroll", onScrollForStats)
  if (countAnimId) cancelAnimationFrame(countAnimId)
})

// ── 数据统计（滚动计数动画）──
const stats = [
  { value: 135, suffix: "", label: "所大学章程", desc: "覆盖 985/211/双一流" },
  { value: 5261, suffix: "", label: "条招生计划", desc: "5 省 2 科类" },
  { value: 23000, suffix: "+", label: "体检限制条款", desc: "教育部指导意见" },
  { value: 5, suffix: "省", label: "数据覆盖", desc: "广东/河南/山东/四川/江苏" },
]
const statDisplays = ref(stats.map(() => "0"))
let countAnimId = 0
let countStarted = false

function animateCount() {
  if (countStarted) return
  countStarted = true
  const duration = 1500
  const startTime = Date.now()

  function tick() {
    const elapsed = Date.now() - startTime
    const progress = Math.min(elapsed / duration, 1)
    // easeOutExpo 缓动
    const eased = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress)

    stats.forEach((s, i) => {
      const current = Math.round(s.value * eased)
      statDisplays.value[i] = current >= 1000 ? current.toLocaleString() : String(current)
    })

    if (progress < 1) {
      countAnimId = window.requestAnimationFrame(tick)
    }
  }
  countAnimId = window.requestAnimationFrame(tick)
}

// 滚动到统计区域时触发计数动画
function onScrollForStats() {
  const statsEl = document.querySelector('.stats-section')
  if (statsEl) {
    const rect = statsEl.getBoundingClientRect()
    if (rect.top < window.innerHeight * 0.8) {
      animateCount()
      window.removeEventListener('scroll', onScrollForStats)
    }
  }
}

onMounted(() => {
  window.addEventListener("scroll", onScroll)
  window.addEventListener("scroll", onScrollForStats)
  // 如果首屏可见，延迟触发
  setTimeout(() => onScrollForStats(), 1000)
})

// ── 功能列表 ──
const features = [
  {
    icon: "shield",
    title: "志愿探雷器",
    tag: "核心功能",
    desc: "粘贴你的志愿草表，AI 逐条审查每所大学的招生章程——体检限制、单科门槛、语种要求、选科匹配，四维交叉比对，在提交前拦截每一处退档风险。",
    highlights: ["135 所大学真实章程", "体检/单科/语种/选科 四维审查", "DANGER / WARNING / PASS 三级定级", "V3 规则引擎 + V4 Agent 双模式"],
    color: "blue",
  },
  {
    icon: "radar",
    title: "捡漏雷达",
    tag: "独家算法",
    desc: "全网扫描新增专业、扩招计划、纯净专业组，六维评分系统锁定绝佳捡漏机遇。数字老虎机滚动 + 狙击锁定入场，每一个机会都不容错过。",
    highlights: ["新增专业 / 扩招专业 / 纯净组识别", "六维评分 + 估分线 + 分差", "联网动态信息（分数线/就业/新闻）", "S 级捡漏预警 + 数据可信度标注"],
    color: "purple",
  },
  {
    icon: "bolt",
    title: "AI 志愿顾问",
    tag: "多轮对话",
    desc: "基于章程知识库 + 雪峰志愿方法论 + 联网搜索，多轮对话深度答疑。你的分数、位次、体检标记全部注入上下文，回答精准可落地。",
    highlights: ["RAG 知识检索 + 联网搜索", "多轮记忆 + 建议追问", "数据可信度 T1-T4 分级", "流式输出，实时反馈"],
    color: "amber",
  },
]

// ── 使用流程 ──
const flowSteps = [
  { num: "01", title: "设置档案", desc: "输入分数、位次、选科、单科成绩、体检视力", icon: "user" },
  { num: "02", title: "粘贴草表", desc: "从考试院系统复制志愿草表，粘贴到探雷器", icon: "database" },
  { num: "03", title: "AI 推演", desc: "七幕仪式序列：唤醒→锁定→抽取→检索→推理→揭晓", icon: "bolt" },
  { num: "04", title: "查看报告", desc: "三色霓虹卡片展示每条志愿的风险等级与条款", icon: "shield" },
]

// ── 真实案例 ──
const cases = [
  {
    scenario: "色弱考生填报临床医学",
    profile: "广东 · 565分 · 物理类 · 色弱",
    result: "DANGER",
    resultText: "极高退档风险",
    detail: "南方医科大学章程明确规定「除法学/管理/外语类外，其他专业不招色盲色弱考生」。探雷器命中该条款，标记 DANGER，避免退档。",
  },
  {
    scenario: "数学 86 分报考数据科学",
    profile: "河南 · 555分 · 物理类 · 数学86",
    result: "WARNING",
    resultText: "需注意",
    detail: "华南理工大学数据科学专业建议数学≥100分。考生 86 分低于门槛，探雷器标记 WARNING 并提示单科风险。",
  },
  {
    scenario: "捡漏新增专业机会",
    profile: "山东 · 580分 · 物理类",
    result: "PASS",
    resultText: "S 级捡漏",
    detail: "雷达扫描到某 985 大学新增「人工智能」专业，计划 30 人，无历史分数线参考。评分 85 分（S 级），分差 +18，触发 S 级捡漏预警。",
  },
]

// ── FAQ ──
const faqs = [
  { q: "数据来源是什么？准确吗？", a: "招生章程来自教育部阳光高考平台，招生计划来自各省考试院。每条数据标注可信度分级（T1 官方数据 → T4 推测），你可以判断参考价值。" },
  { q: "AI 审查能替代人工核对吗？", a: "不能。本工具是辅助筛查工具，基于 AI 理解章程条款，存在理解偏差可能。最终填报前请务必核对官方《填报指南》与高校官网章程。" },
  { q: "支持哪些省份？", a: "目前覆盖广东、河南、山东、四川、江苏 5 省的招生计划数据。章程规则库覆盖全国 135 所 985/211/双一流高校，其他省份也可使用探雷器和 AI 顾问。" },
  { q: "收费吗？", a: "探雷器和 AI 顾问完全免费。捡漏雷达前 5 条结果免费查看，解锁全部结果需支付 ¥9.9（当前为模拟支付模式）。" },
  { q: "我的档案数据安全吗？", a: "档案仅存储在浏览器本地（localStorage）和后端数据库（用于跨设备同步），不向第三方分享。可随时在「我的」页面删除。" },
]
const expandedFaq = ref<number | null>(0)
function toggleFaq(i: number) { expandedFaq.value = expandedFaq.value === i ? null : i }
</script>

<template>
  <div class="landing-shell">
    <!-- 背景 -->
    <div class="bg-ambient">
      <div class="orb orb-1" />
      <div class="orb orb-2" />
      <div class="orb orb-3" />
      <div class="grid-overlay" />
    </div>

    <!-- ═══ 导航栏 ═══ -->
    <nav class="nav-bar" :class="{ scrolled }">
      <div class="nav-inner">
        <div class="brand" @click="router.push('/')">
          <div class="brand-mark"><Icon name="shield" :size="16" /></div>
          <span class="brand-text">GAOKAO<span class="brand-accent">·</span>SNIPER</span>
        </div>
        <div class="nav-links">
          <span @click="scrollToSection('features')" class="nav-link">功能</span>
          <span @click="scrollToSection('how')" class="nav-link">使用流程</span>
          <span @click="scrollToSection('cases')" class="nav-link">真实案例</span>
          <span @click="scrollToSection('faq')" class="nav-link">常见问题</span>
        </div>
        <div class="nav-cta" @click="goToWorkbench">
          <span>立即使用</span>
          <Icon name="arrowRight" :size="14" />
        </div>
      </div>
    </nav>

    <!-- ═══ Hero ═══ -->
    <section class="hero">
      <div class="hero-content">
        <Transition name="hero-fade" appear>
          <div class="hero-badge">
            <span class="badge-dot" />
            <span>2026 高考志愿审查引擎 · 已就绪</span>
          </div>
        </Transition>

        <Transition name="hero-fade" appear>
          <h1 class="hero-title">
            <span class="title-line">别让一分之差</span>
            <span class="title-line title-accent">毁掉十二年寒窗</span>
          </h1>
        </Transition>

        <Transition name="hero-fade" appear>
          <p class="hero-desc">
            每年超过 <strong>30%</strong> 的退档因体检限制、单科不达标、语种不符而起。<br/>
            GAOKAO·SNIPER 基于 135 所大学真实招生章程，AI 逐条审查你的志愿草表，<br/>
            在你点击「提交」之前，拦截每一处致命风险。
          </p>
        </Transition>

        <Transition name="hero-fade" appear>
          <div class="hero-actions">
            <div class="cta-primary" @click="goToWorkbench">
              <Icon name="bolt" :size="18" />
              <span>{{ profileStore.isProfileComplete ? '免费开始推演' : '开始使用' }}</span>
            </div>
            <div class="cta-secondary" @click="router.push('/pages/profile/profile')">
              <Icon name="user" :size="16" />
              <span>{{ profileStore.isProfileComplete ? '查看我的档案' : '先设置我的档案' }}</span>
            </div>
          </div>
        </Transition>

        <Transition name="hero-fade" appear>
          <div class="hero-trust">
            <span class="trust-item"><Icon name="check" :size="12" /> 无需注册</span>
            <span class="trust-item"><Icon name="check" :size="12" /> 数据本地存储</span>
            <span class="trust-item"><Icon name="check" :size="12" /> 探雷器永久免费</span>
          </div>
        </Transition>
      </div>
    </section>

    <!-- ═══ 数据统计 ═══ -->
    <section class="stats-section">
      <div class="stats-bar">
        <div v-for="(s, i) in stats" :key="s.label" class="stat-cell">
          <span class="stat-value">{{ statDisplays[i] }}<span class="stat-suffix">{{ s.suffix }}</span></span>
          <span class="stat-label">{{ s.label }}</span>
          <span class="stat-desc">{{ s.desc }}</span>
        </div>
      </div>
    </section>

    <!-- ═══ 功能详解 ═══ -->
    <section id="features" class="features-section">
      <div class="section-header">
        <span class="section-kicker">三大核心引擎</span>
        <h2 class="section-title">从排雷到捡漏，再到 AI 答疑</h2>
        <p class="section-sub">每一个功能都基于真实数据，每一次审查都可溯源到具体章程条款</p>
      </div>

      <div class="features-list">
        <div v-for="(f, i) in features" :key="f.title" class="feature-block" :class="'color-' + f.color">
          <div class="feature-left">
            <div class="feature-icon-big"><Icon :name="f.icon" :size="32" /></div>
            <span class="feature-tag">{{ f.tag }}</span>
          </div>
          <div class="feature-right">
            <h3 class="feature-name">{{ f.title }}</h3>
            <p class="feature-desc">{{ f.desc }}</p>
            <div class="feature-highlights">
              <div v-for="h in f.highlights" :key="h" class="highlight-item">
                <Icon name="check" :size="12" />
                <span>{{ h }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ 使用流程 ═══ -->
    <section id="how" class="flow-section">
      <div class="section-header">
        <span class="section-kicker">四步完成</span>
        <h2 class="section-title">从草表到报告，只需 30 秒</h2>
      </div>
      <div class="flow-grid">
        <div v-for="(step, i) in flowSteps" :key="step.num" class="flow-card">
          <div class="flow-card-head">
            <span class="flow-num">{{ step.num }}</span>
            <div class="flow-icon"><Icon :name="step.icon" :size="20" /></div>
          </div>
          <h4 class="flow-title">{{ step.title }}</h4>
          <p class="flow-desc">{{ step.desc }}</p>
          <div v-if="i < flowSteps.length - 1" class="flow-arrow"><Icon name="arrowRight" :size="16" /></div>
        </div>
      </div>
    </section>

    <!-- ═══ 真实案例 ═══ -->
    <section id="cases" class="cases-section">
      <div class="section-header">
        <span class="section-kicker">真实场景</span>
        <h2 class="section-title">这些退档风险，你能自己发现吗？</h2>
        <p class="section-sub">以下案例均基于真实招生章程条款，探雷器全部命中</p>
      </div>
      <div class="cases-grid">
        <div v-for="c in cases" :key="c.scenario" class="case-card glass-card">
          <div class="case-header">
            <span class="case-scenario">{{ c.scenario }}</span>
            <span class="case-result-badge" :class="'result-' + c.result.toLowerCase()">{{ c.resultText }}</span>
          </div>
          <div class="case-profile"><Icon name="user" :size="11" /> {{ c.profile }}</div>
          <p class="case-detail">{{ c.detail }}</p>
        </div>
      </div>
    </section>

    <!-- ═══ FAQ ═══ -->
    <section id="faq" class="faq-section">
      <div class="section-header">
        <span class="section-kicker">常见问题</span>
        <h2 class="section-title">你可能想问的</h2>
      </div>
      <div class="faq-list">
        <div v-for="(f, i) in faqs" :key="i" class="faq-item" :class="{ expanded: expandedFaq === i }">
          <div class="faq-q" @click="toggleFaq(i)">
            <span class="faq-q-text">{{ f.q }}</span>
            <span class="faq-toggle" :class="{ rotated: expandedFaq === i }">+</span>
          </div>
          <Transition name="faq-expand">
            <div v-if="expandedFaq === i" class="faq-a">
              <p>{{ f.a }}</p>
            </div>
          </Transition>
        </div>
      </div>
    </section>

    <!-- ═══ 最终 CTA ═══ -->
    <section class="final-cta">
      <div class="cta-box glass-card">
        <h2 class="cta-title">你的志愿表，经得起推演吗？</h2>
        <p class="cta-desc">粘贴草表，30 秒内获得完整风险报告。免费、无需注册。</p>
        <div class="cta-btn-large" @click="goToWorkbench">
          <Icon name="bolt" :size="20" />
          <span>开始推演计算</span>
        </div>
      </div>
    </section>

    <!-- ═══ Footer ═══ -->
    <footer class="landing-footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <div class="brand-mark small"><Icon name="shield" :size="12" /></div>
          <span>GAOKAO·SNIPER</span>
        </div>
        <span class="footer-disclaimer">本工具数据来源于各省考试院与公开招生章程，受限于数据更新延迟与 AI 理解能力，仅作辅助筛查，不构成填报承诺。考生须最终核对官方《填报指南》与官网章程。</span>
        <span class="footer-copy">© 2026 GAOKAO SNIPER · v0.7.0 BETA</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.landing-shell { min-height: 100vh; background: #020617; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Inter", "SF Pro Display", sans-serif; position: relative; overflow-x: hidden; }

/* ── 背景 ── */
.bg-ambient { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
.orb { position: absolute; border-radius: 50%; filter: blur(120px); }
.orb-1 { width: 600px; height: 600px; background: radial-gradient(circle, #38bdf8, transparent); top: -200px; left: -100px; opacity: 0.12; }
.orb-2 { width: 500px; height: 500px; background: radial-gradient(circle, #818cf8, transparent); top: 40%; right: -100px; opacity: 0.1; }
.orb-3 { width: 400px; height: 400px; background: radial-gradient(circle, #facc15, transparent); bottom: -100px; left: 30%; opacity: 0.05; }
.grid-overlay { position: absolute; inset: 0; background-image: linear-gradient(rgba(56, 189, 248, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(56, 189, 248, 0.03) 1px, transparent 1px); background-size: 60px 60px; mask: linear-gradient(to bottom, transparent, black 30%, black 70%, transparent); -webkit-mask: linear-gradient(to bottom, transparent, black 30%, black 70%, transparent); }

/* ── 导航栏 ── */
.nav-bar { position: fixed; top: 0; left: 0; right: 0; z-index: 100; transition: all 0.3s ease; }
.nav-bar.scrolled { background: rgba(2, 6, 23, 0.85); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.nav-inner { max-width: 1100px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; padding: 16px 24px; }
.brand { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.brand-mark { width: 32px; height: 32px; background: linear-gradient(135deg, #38bdf8, #818cf8); border-radius: 9px; display: flex; align-items: center; justify-content: center; color: #fff; box-shadow: 0 0 24px rgba(56, 189, 248, 0.3); }
.brand-mark.small { width: 24px; height: 24px; border-radius: 6px; box-shadow: none; }
.brand-text { font-size: 18px; font-weight: 900; color: #f1f5f9; letter-spacing: -0.5px; }
.brand-accent { color: #38bdf8; }
.nav-links { display: flex; gap: 28px; }
.nav-link { font-size: 13px; color: #94a3b8; font-weight: 500; transition: color 0.2s; cursor: pointer; }
.nav-link:hover { color: #38bdf8; }
.nav-cta { display: flex; align-items: center; gap: 6px; padding: 8px 18px; background: linear-gradient(135deg, #38bdf8, #818cf8); border-radius: 10px; color: #fff; font-size: 13px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
.nav-cta:hover { box-shadow: 0 6px 20px rgba(56, 189, 248, 0.35); transform: translateY(-1px); }

/* ── Hero ── */
.hero { position: relative; z-index: 1; min-height: 90vh; display: flex; align-items: center; justify-content: center; padding: 100px 24px 60px; }
.hero-content { max-width: 760px; text-align: center; }
.hero-badge { display: inline-flex; align-items: center; gap: 8px; padding: 7px 18px; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 20px; margin-bottom: 28px; }
.badge-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 10px rgba(34, 197, 94, 0.6); animation: badge-pulse 2s ease-in-out infinite; }
@keyframes badge-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.hero-badge span:last-child { font-size: 13px; color: #7dd3fc; font-weight: 600; letter-spacing: 0.5px; }
.hero-title { font-size: 56px; font-weight: 900; line-height: 1.15; letter-spacing: -2px; margin: 0 0 24px; display: flex; flex-direction: column; gap: 6px; }
.title-line { color: #f1f5f9; }
.title-accent { background: linear-gradient(135deg, #38bdf8, #818cf8); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.hero-desc { font-size: 15px; color: #94a3b8; font-weight: 300; line-height: 1.9; margin: 0 0 36px; }
.hero-desc strong { color: #fda4af; font-weight: 600; }
.hero-actions { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; margin-bottom: 24px; }
.cta-primary { display: flex; align-items: center; gap: 8px; padding: 15px 36px; background: linear-gradient(135deg, #38bdf8, #818cf8); border-radius: 12px; color: #fff; font-size: 16px; font-weight: 700; cursor: pointer; box-shadow: 0 8px 32px rgba(56, 189, 248, 0.3); transition: all 0.2s; }
.cta-primary:hover { box-shadow: 0 12px 40px rgba(56, 189, 248, 0.45); transform: translateY(-2px); }
.cta-primary:active { transform: scale(0.97); }
.cta-secondary { display: flex; align-items: center; gap: 6px; padding: 15px 28px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: #94a3b8; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.cta-secondary:hover { background: rgba(255, 255, 255, 0.08); color: #e2e8f0; border-color: rgba(255, 255, 255, 0.2); }
.hero-trust { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; }
.trust-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #64748b; }
.trust-item svg { color: #34d399; }

/* ── 通用 section ── */
.section-header { text-align: center; max-width: 640px; margin: 0 auto 48px; padding: 0 24px; }
.section-kicker { display: inline-block; font-size: 11px; font-weight: 700; color: #38bdf8; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 12px; }
.section-title { font-size: 36px; font-weight: 900; color: #f1f5f9; letter-spacing: -1px; margin: 0 0 12px; line-height: 1.2; }
.section-sub { font-size: 14px; color: #64748b; font-weight: 300; line-height: 1.7; margin: 0; }

/* ── 统计 ── */
.stats-section { position: relative; z-index: 1; padding: 0 24px 80px; display: flex; justify-content: center; }
.stats-bar { display: flex; gap: 0; padding: 28px 40px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 16px; max-width: 800px; width: 100%; box-sizing: border-box; }
.stat-cell { flex: 1; text-align: center; border-right: 1px solid rgba(255, 255, 255, 0.06); padding: 0 8px; }
.stat-cell:last-child { border-right: none; }
.stat-value { font-size: 32px; font-weight: 900; color: #f1f5f9; display: block; font-family: "SF Mono", monospace; letter-spacing: -1px; }
.stat-suffix { font-size: 18px; color: #38bdf8; }
.stat-label { font-size: 12px; color: #94a3b8; font-weight: 600; margin-top: 4px; display: block; }
.stat-desc { font-size: 10px; color: #475569; margin-top: 2px; display: block; }

/* ── 功能详解 ── */
.features-section { position: relative; z-index: 1; padding: 80px 24px; max-width: 1000px; margin: 0 auto; }
.features-list { display: flex; flex-direction: column; gap: 20px; }
.feature-block { display: flex; gap: 24px; padding: 28px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 16px; transition: all 0.3s; }
.feature-block:hover { border-color: rgba(56, 189, 248, 0.15); background: rgba(255, 255, 255, 0.035); }
.feature-block.color-blue { border-left: 3px solid #38bdf8; }
.feature-block.color-purple { border-left: 3px solid #818cf8; }
.feature-block.color-amber { border-left: 3px solid #fbbf24; }
.feature-left { display: flex; flex-direction: column; align-items: center; gap: 10px; flex-shrink: 0; }
.feature-icon-big { width: 56px; height: 56px; border-radius: 14px; display: flex; align-items: center; justify-content: center; }
.color-blue .feature-icon-big { background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.2); }
.color-purple .feature-icon-big { background: rgba(129, 140, 248, 0.12); color: #818cf8; border: 1px solid rgba(129, 140, 248, 0.2); }
.color-amber .feature-icon-big { background: rgba(251, 191, 36, 0.12); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.2); }
.feature-tag { font-size: 9px; font-weight: 700; color: #64748b; letter-spacing: 1px; text-transform: uppercase; padding: 2px 8px; background: rgba(255, 255, 255, 0.05); border-radius: 4px; }
.feature-right { flex: 1; }
.feature-name { font-size: 20px; font-weight: 800; color: #f1f5f9; margin: 0 0 8px; }
.feature-desc { font-size: 13px; color: #94a3b8; line-height: 1.7; margin: 0 0 14px; font-weight: 300; }
.feature-highlights { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.highlight-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #64748b; }
.highlight-item svg { color: #34d399; flex-shrink: 0; }

/* ── 使用流程 ── */
.flow-section { position: relative; z-index: 1; padding: 80px 24px; max-width: 1000px; margin: 0 auto; }
.flow-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.flow-card { position: relative; padding: 24px 20px; background: rgba(255, 255, 255, 0.025); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 14px; }
.flow-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.flow-num { font-size: 28px; font-weight: 900; color: #38bdf8; font-family: "SF Mono", monospace; text-shadow: 0 0 12px rgba(56, 189, 248, 0.3); }
.flow-icon { width: 36px; height: 36px; border-radius: 10px; background: rgba(56, 189, 248, 0.1); display: flex; align-items: center; justify-content: center; color: #38bdf8; }
.flow-title { font-size: 15px; font-weight: 700; color: #f1f5f9; margin: 0 0 6px; }
.flow-desc { font-size: 11px; color: #64748b; line-height: 1.6; margin: 0; }
.flow-arrow { position: absolute; right: -10px; top: 50%; transform: translateY(-50%); color: #334155; z-index: 2; }

/* ── 真实案例 ── */
.cases-section { position: relative; z-index: 1; padding: 80px 24px; max-width: 1000px; margin: 0 auto; }
.cases-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.case-card { padding: 22px; display: flex; flex-direction: column; gap: 10px; }
.case-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.case-scenario { font-size: 14px; font-weight: 700; color: #f1f5f9; line-height: 1.4; }
.case-result-badge { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 5px; white-space: nowrap; flex-shrink: 0; }
.result-danger { background: rgba(251, 113, 133, 0.12); color: #fda4af; border: 1px solid rgba(251, 113, 133, 0.2); }
.result-warning { background: rgba(251, 191, 36, 0.12); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.2); }
.result-pass { background: rgba(52, 211, 153, 0.12); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.2); }
.case-profile { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #7dd3fc; font-family: "SF Mono", monospace; }
.case-detail { font-size: 12px; color: #94a3b8; line-height: 1.7; margin: 0; font-weight: 300; }

/* ── FAQ ── */
.faq-section { position: relative; z-index: 1; padding: 80px 24px; max-width: 720px; margin: 0 auto; }
.faq-list { display: flex; flex-direction: column; gap: 10px; }
.faq-item { background: rgba(255, 255, 255, 0.025); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 12px; overflow: hidden; transition: all 0.2s; }
.faq-item.expanded { border-color: rgba(56, 189, 248, 0.15); background: rgba(56, 189, 248, 0.03); }
.faq-q { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; cursor: pointer; }
.faq-q-text { font-size: 14px; font-weight: 600; color: #e2e8f0; }
.faq-toggle { font-size: 20px; color: #38bdf8; transition: transform 0.3s; }
.faq-toggle.rotated { transform: rotate(45deg); }
.faq-a { padding: 0 20px 16px; }
.faq-a p { font-size: 13px; color: #94a3b8; line-height: 1.7; margin: 0; font-weight: 300; }
.faq-expand-enter-active, .faq-expand-leave-active { transition: all 0.3s ease; }
.faq-expand-enter-from, .faq-expand-leave-to { opacity: 0; max-height: 0; }
.faq-expand-enter-to, .faq-expand-leave-from { opacity: 1; max-height: 200px; }

/* ── 最终 CTA ── */
.final-cta { position: relative; z-index: 1; padding: 60px 24px 80px; display: flex; justify-content: center; }
.cta-box { text-align: center; padding: 48px 40px; max-width: 560px; width: 100%; }
.cta-title { font-size: 28px; font-weight: 900; color: #f1f5f9; margin: 0 0 12px; letter-spacing: -1px; }
.cta-desc { font-size: 14px; color: #94a3b8; margin: 0 0 28px; font-weight: 300; }
.cta-btn-large { display: inline-flex; align-items: center; gap: 8px; padding: 16px 40px; background: linear-gradient(135deg, #38bdf8, #818cf8); border-radius: 14px; color: #fff; font-size: 17px; font-weight: 700; cursor: pointer; box-shadow: 0 8px 32px rgba(56, 189, 248, 0.35); transition: all 0.2s; }
.cta-btn-large:hover { box-shadow: 0 12px 44px rgba(56, 189, 248, 0.5); transform: translateY(-2px); }
.cta-btn-large:active { transform: scale(0.97); }

/* ── Footer ── */
.landing-footer { position: relative; z-index: 1; padding: 40px 24px; border-top: 1px solid rgba(255, 255, 255, 0.04); }
.footer-inner { max-width: 700px; margin: 0 auto; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.footer-brand { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: #64748b; }
.footer-disclaimer { font-size: 11px; color: #334155; line-height: 1.7; max-width: 560px; }
.footer-copy { font-size: 11px; color: #1e293b; font-family: "SF Mono", monospace; }

/* ── Transitions ── */
.hero-fade-enter-active { transition: all 0.8s cubic-bezier(0.25, 0.8, 0.25, 1); }
.hero-fade-enter-from { opacity: 0; transform: translateY(20px); }
.hero-fade-enter-active:nth-child(2) { transition-delay: 0.1s; }
.hero-fade-enter-active:nth-child(3) { transition-delay: 0.2s; }
.hero-fade-enter-active:nth-child(4) { transition-delay: 0.3s; }
.hero-fade-enter-active:nth-child(5) { transition-delay: 0.4s; }

/* ── 响应式 ── */
@media (max-width: 768px) {
  .nav-inner { padding: 12px 16px; }
  .nav-links { display: none; }
  .hero { min-height: auto; padding: 100px 16px 40px; }
  .hero-title { font-size: 36px; }
  .hero-desc { font-size: 13px; }
  .hero-desc br { display: none; }
  .hero-actions { flex-direction: column; align-items: stretch; }
  .cta-primary, .cta-secondary { justify-content: center; }
  .hero-trust { flex-direction: column; gap: 6px; }
  .stats-bar { flex-wrap: wrap; gap: 16px; padding: 20px; }
  .stat-cell { flex: 1 1 40%; border-right: none; border-bottom: 1px solid rgba(255, 255, 255, 0.06); padding-bottom: 12px; }
  .stat-cell:nth-last-child(-n+2) { border-bottom: none; padding-bottom: 0; }
  .stat-value { font-size: 24px; }
  .section-title { font-size: 26px; }
  .features-section, .flow-section, .cases-section, .faq-section { padding: 48px 16px; }
  .feature-block { flex-direction: column; gap: 16px; padding: 20px; }
  .feature-left { flex-direction: row; }
  .feature-highlights { grid-template-columns: 1fr; }
  .flow-grid { grid-template-columns: 1fr 1fr; }
  .flow-arrow { display: none; }
  .cases-grid { grid-template-columns: 1fr; }
  .cta-box { padding: 32px 20px; }
  .cta-title { font-size: 22px; }
  .cta-btn-large { padding: 14px 28px; font-size: 15px; }
}
</style>
