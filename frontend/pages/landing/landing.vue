<!--
  pages/landing/landing.vue — 产品主页（宣传+引导）
  结构：导航栏 → Hero 痛点共鸣 → 数据权威 → 三大功能 → 使用流程 → 真实案例 → FAQ → CTA → Footer
-->
<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from "vue"
import { useRouter } from "vue-router"
import { useProfileStore } from "../../stores/profile"
import Icon from "../../components/Icon.vue"
import ThemeToggle from "../../components/ThemeToggle.vue"

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
    desc: "把你的志愿草表贴进来，我们逐所核对 135 所大学的招生章程——体检限制、单科门槛、语种要求、选科匹配，每一处都帮你看到，在你提交之前。",
    highlights: ["135 所大学真实章程", "体检/单科/语种/选科 四维核对", "三级风险标注，逐条给出条款出处", "联网检索最新章程，不留盲区"],
    color: "blue",
  },
  {
    icon: "radar",
    title: "捡漏雷达",
    tag: "独家算法",
    desc: "扫描新增专业、扩招计划、纯净专业组，六维评分帮你筛出值得关注的院校。每一个机会，都附上数据出处和可信度，让你心里有底。",
    highlights: ["新增专业 / 扩招专业 / 纯净组识别", "六维评分 + 估分线 + 分差", "联网动态信息（分数线/就业/新闻）", "重点推荐标注 + 数据可信度分级"],
    color: "purple",
  },
  {
    icon: "bolt",
    title: "AI 志愿顾问",
    tag: "多轮对话",
    desc: "把你的困惑问出来。基于章程知识库与联网搜索，多轮对话深度答疑。你的分数、位次、体检情况都记在上下文里，回答具体可落地。",
    highlights: ["章程知识库 + 联网搜索", "多轮记忆，越聊越懂你", "数据可信度分级，告诉你哪些可参考", "流式输出，边答边看"],
    color: "amber",
  },
]

// ── 使用流程 ──
const flowSteps = [
  { num: "01", title: "填写档案", desc: "输入分数、位次、选科、单科成绩、体检视力", icon: "user" },
  { num: "02", title: "粘贴草表", desc: "从考试院系统复制志愿草表，贴到探雷器", icon: "scroll" },
  { num: "03", title: "逐所核对", desc: "研墨→展卷→列目→查典→研判→成文，逐条对照章程", icon: "candle" },
  { num: "04", title: "查看报告", desc: "每一所都标注风险等级与具体条款，可溯源", icon: "shield" },
]

// ── 真实案例 ──
const cases = [
  {
    scenario: "色弱考生填报临床医学",
    profile: "广东 · 565分 · 物理类 · 色弱",
    result: "DANGER",
    resultText: "务必重视",
    detail: "南方医科大学章程明确规定「除法学/管理/外语类外，其他专业不招色盲色弱考生」。我们核到了这条，标注「务必重视」，避免你提交后被退档。",
  },
  {
    scenario: "数学 86 分报考数据科学",
    profile: "河南 · 555分 · 物理类 · 数学86",
    result: "WARNING",
    resultText: "需要留意",
    detail: "华南理工大学数据科学专业建议数学≥100分。你 86 分低于门槛，我们标为「需要留意」，并附上章程原文供你判断。",
  },
  {
    scenario: "发现值得重点关注的院校",
    profile: "山东 · 580分 · 物理类",
    result: "PASS",
    resultText: "重点推荐",
    detail: "雷达扫到某 985 大学新增「人工智能」专业，计划 30 人，无历史分数线参考。评分 85 分，分差 +18，标为「重点推荐」，附上数据出处。",
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
          <span class="brand-text">志愿守护</span>
        </div>
        <div class="nav-links">
          <span @click="scrollToSection('features')" class="nav-link">功能</span>
          <span @click="scrollToSection('how')" class="nav-link">使用流程</span>
          <span @click="scrollToSection('cases')" class="nav-link">真实案例</span>
          <span @click="scrollToSection('faq')" class="nav-link">常见问题</span>
        </div>
        <div class="nav-right">
          <ThemeToggle />
          <div class="nav-cta" @click="goToWorkbench">
            <span>立即使用</span>
            <Icon name="arrowRight" :size="14" />
          </div>
        </div>
      </div>
    </nav>

    <!-- ═══ Hero ═══ -->
    <section class="hero">
      <div class="hero-content">
        <Transition name="hero-fade" appear>
          <div class="hero-badge">
            <span class="badge-dot" />
            <span>2026 招生章程已收录 · 我们在这里</span>
          </div>
        </Transition>

        <Transition name="hero-fade" appear>
          <h1 class="hero-title">
            <span class="title-line">十二年寒窗</span>
            <span class="title-line title-accent">值得一份安心的志愿表</span>
          </h1>
        </Transition>

        <Transition name="hero-fade" appear>
          <p class="hero-desc">
            每年都有考生，因为漏看了章程里的体检限制、单科门槛，<br/>
            填完才发现报不了。我们逐所核对你草表里的每一所大学，<br/>
            在你点「提交」之前，把需要留意的地方告诉你。
          </p>
        </Transition>

        <Transition name="hero-fade" appear>
          <div class="hero-poetry">
            <span class="poetry-line font-brush">长风破浪会有时</span>
            <span class="poetry-sub">— 李白·行路难</span>
          </div>
        </Transition>

        <Transition name="hero-fade" appear>
          <div class="hero-actions">
            <div class="cta-primary" @click="goToWorkbench">
              <Icon name="candle" :size="18" />
              <span>{{ profileStore.isProfileComplete ? '免费开始核对' : '开始使用' }}</span>
            </div>
            <div class="cta-secondary" @click="router.push('/pages/profile/profile')">
              <Icon name="user" :size="16" />
              <span>{{ profileStore.isProfileComplete ? '查看我的档案' : '先填我的档案' }}</span>
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
        <span class="section-kicker">三大功能</span>
        <h2 class="section-title">从核对到发现，再到答疑解惑</h2>
        <p class="section-sub">每一个功能都基于真实章程，每一条结论都可溯源到具体条款</p>
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
        <h2 class="section-title">从草表到报告，逐所核对</h2>
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
        <h2 class="section-title">这些藏在章程里的细节，我们帮你看到</h2>
        <p class="section-sub">以下案例均基于真实招生章程条款，全部命中</p>
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
        <h2 class="cta-title">你的志愿表，我们陪你核对一遍</h2>
        <p class="cta-desc">贴上草表，逐所核对每一处风险。免费、无需注册。</p>
        <div class="cta-btn-large" @click="goToWorkbench">
          <Icon name="candle" :size="20" />
          <span>开始核对志愿</span>
        </div>
      </div>
    </section>

    <!-- ═══ Footer ═══ -->
    <footer class="landing-footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <div class="brand-mark small"><Icon name="shield" :size="12" /></div>
          <span>志愿守护</span>
        </div>
        <span class="footer-wish font-brush">愿你心之所向，皆能如愿。</span>
        <span class="footer-disclaimer">本工具数据来源于各省考试院与公开招生章程，受限于数据更新延迟与 AI 理解能力，仅作辅助筛查，不构成填报承诺。考生须最终核对官方《填报指南》与官网章程。</span>
        <span class="footer-copy">© 2026 志愿守护 · v0.8.0</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.landing-shell { min-height: 100vh; background: var(--ink-900); color: var(--text-primary); font-family: var(--font-sans); position: relative; overflow-x: hidden; }

/* ── 背景 ── */
.bg-ambient { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
.orb { position: absolute; border-radius: 50%; filter: blur(120px); }
.orb-1 { width: 600px; height: 600px; background: radial-gradient(circle, #e8b974, transparent); top: -200px; left: -100px; opacity: 0.12; }
.orb-2 { width: 500px; height: 500px; background: radial-gradient(circle, #d49a4e, transparent); top: 40%; right: -100px; opacity: 0.1; }
.orb-3 { width: 400px; height: 400px; background: radial-gradient(circle, #facc15, transparent); bottom: -100px; left: 30%; opacity: 0.05; }
.grid-overlay { position: absolute; inset: 0; background-image: linear-gradient(rgba(232, 185, 116, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(232, 185, 116, 0.03) 1px, transparent 1px); background-size: 60px 60px; mask: linear-gradient(to bottom, transparent, black 30%, black 70%, transparent); -webkit-mask: linear-gradient(to bottom, transparent, black 30%, black 70%, transparent); }

/* ── 导航栏 ── */
.nav-bar { position: fixed; top: 0; left: 0; right: 0; z-index: 100; transition: all 0.3s ease; }
.nav-bar.scrolled { background: rgba(2, 6, 23, 0.85); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255, 255, 255, 0.06); }
.nav-inner { max-width: 1100px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; padding: 16px 24px; }
.brand { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.brand-mark { width: 32px; height: 32px; background: linear-gradient(135deg, #e8b974, #d49a4e); border-radius: 9px; display: flex; align-items: center; justify-content: center; color: #fff; box-shadow: 0 0 24px rgba(232, 185, 116, 0.3); }
.brand-mark.small { width: 24px; height: 24px; border-radius: 6px; box-shadow: none; }
.brand-text { font-size: 18px; font-weight: 900; color: var(--text-primary); letter-spacing: -0.5px; }
.brand-accent { color: #e8b974; }
.nav-links { display: flex; gap: 28px; }
.nav-right { display: flex; align-items: center; gap: 12px; }
.nav-link { font-size: 13px; color: var(--text-secondary); font-weight: 500; transition: color 0.2s; cursor: pointer; }
.nav-link:hover { color: #e8b974; }
.nav-cta { display: flex; align-items: center; gap: 6px; padding: 8px 18px; background: linear-gradient(135deg, #e8b974, #d49a4e); border-radius: 10px; color: #fff; font-size: 13px; font-weight: 700; cursor: pointer; transition: all 0.2s; }
.nav-cta:hover { box-shadow: 0 6px 20px rgba(232, 185, 116, 0.35); transform: translateY(-1px); }

/* ── Hero ── */
.hero { position: relative; z-index: 1; min-height: 90vh; display: flex; align-items: center; justify-content: center; padding: 100px 24px 60px; }
.hero-content { max-width: 760px; text-align: center; }
.hero-badge { display: inline-flex; align-items: center; gap: 8px; padding: 7px 18px; background: rgba(232, 185, 116, 0.08); border: 1px solid rgba(232, 185, 116, 0.2); border-radius: 20px; margin-bottom: 28px; }
.badge-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 10px rgba(34, 197, 94, 0.6); animation: badge-pulse 2s ease-in-out infinite; }
@keyframes badge-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
.hero-badge span:last-child { font-size: 13px; color: #f4d8a8; font-weight: 600; letter-spacing: 0.5px; }
.hero-title { font-size: 56px; font-weight: 900; line-height: 1.15; letter-spacing: -2px; margin: 0 0 24px; display: flex; flex-direction: column; gap: 6px; }
.title-line { color: var(--text-primary); }
.title-accent { background: linear-gradient(135deg, #e8b974, #d49a4e); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }
.hero-desc { font-size: 15px; color: var(--text-secondary); font-weight: 300; line-height: 1.9; margin: 0 0 24px; }
.hero-desc strong { color: #e8b974; font-weight: 600; }
.hero-poetry { margin: 0 0 36px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.hero-poetry .poetry-line { font-size: 22px; color: #f4d8a8; letter-spacing: 0.15em; text-shadow: 0 0 20px rgba(232, 185, 116, 0.25); }
.hero-poetry .poetry-sub { font-size: 11px; color: var(--text-muted); letter-spacing: 0.1em; }
.hero-actions { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; margin-bottom: 24px; }
.cta-primary { display: flex; align-items: center; gap: 8px; padding: 15px 36px; background: linear-gradient(135deg, #e8b974, #d49a4e); border-radius: 12px; color: #fff; font-size: 16px; font-weight: 700; cursor: pointer; box-shadow: 0 8px 32px rgba(232, 185, 116, 0.3); transition: all 0.2s; }
.cta-primary:hover { box-shadow: 0 12px 40px rgba(232, 185, 116, 0.45); transform: translateY(-2px); }
.cta-primary:active { transform: scale(0.97); }
.cta-secondary { display: flex; align-items: center; gap: 6px; padding: 15px 28px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; color: var(--text-secondary); font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.cta-secondary:hover { background: rgba(255, 255, 255, 0.08); color: var(--text-primary); border-color: rgba(255, 255, 255, 0.2); }
.hero-trust { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; }
.trust-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--text-muted); }
.trust-item svg { color: #34d399; }

/* ── 通用 section ── */
.section-header { text-align: center; max-width: 640px; margin: 0 auto 48px; padding: 0 24px; }
.section-kicker { display: inline-block; font-size: 11px; font-weight: 700; color: #e8b974; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 12px; }
.section-title { font-size: 36px; font-weight: 900; color: var(--text-primary); letter-spacing: -1px; margin: 0 0 12px; line-height: 1.2; }
.section-sub { font-size: 14px; color: var(--text-muted); font-weight: 300; line-height: 1.7; margin: 0; }

/* ── 统计 ── */
.stats-section { position: relative; z-index: 1; padding: 0 24px 80px; display: flex; justify-content: center; }
.stats-bar { display: flex; gap: 0; padding: 28px 40px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 16px; max-width: 800px; width: 100%; box-sizing: border-box; }
.stat-cell { flex: 1; text-align: center; border-right: 1px solid rgba(255, 255, 255, 0.06); padding: 0 8px; }
.stat-cell:last-child { border-right: none; }
.stat-value { font-size: 32px; font-weight: 900; color: var(--text-primary); display: block; font-family: "SF Mono", monospace; letter-spacing: -1px; }
.stat-suffix { font-size: 18px; color: #e8b974; }
.stat-label { font-size: 12px; color: var(--text-secondary); font-weight: 600; margin-top: 4px; display: block; }
.stat-desc { font-size: 10px; color: #475569; margin-top: 2px; display: block; }

/* ── 功能详解 ── */
.features-section { position: relative; z-index: 1; padding: 80px 24px; max-width: 1000px; margin: 0 auto; }
.features-list { display: flex; flex-direction: column; gap: 20px; }
.feature-block { display: flex; gap: 24px; padding: 28px; background: rgba(255, 255, 255, 0.02); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 16px; transition: all 0.3s; }
.feature-block:hover { border-color: rgba(232, 185, 116, 0.15); background: rgba(255, 255, 255, 0.035); }
.feature-block.color-blue { border-left: 3px solid #e8b974; }
.feature-block.color-purple { border-left: 3px solid #d49a4e; }
.feature-block.color-amber { border-left: 3px solid #fbbf24; }
.feature-left { display: flex; flex-direction: column; align-items: center; gap: 10px; flex-shrink: 0; }
.feature-icon-big { width: 56px; height: 56px; border-radius: 14px; display: flex; align-items: center; justify-content: center; }
.color-blue .feature-icon-big { background: rgba(232, 185, 116, 0.12); color: #e8b974; border: 1px solid rgba(232, 185, 116, 0.2); }
.color-purple .feature-icon-big { background: rgba(212, 154, 78, 0.12); color: #d49a4e; border: 1px solid rgba(212, 154, 78, 0.2); }
.color-amber .feature-icon-big { background: rgba(251, 191, 36, 0.12); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.2); }
.feature-tag { font-size: 9px; font-weight: 700; color: var(--text-muted); letter-spacing: 1px; text-transform: uppercase; padding: 2px 8px; background: rgba(255, 255, 255, 0.05); border-radius: 4px; }
.feature-right { flex: 1; }
.feature-name { font-size: 20px; font-weight: 800; color: var(--text-primary); margin: 0 0 8px; }
.feature-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin: 0 0 14px; font-weight: 300; }
.feature-highlights { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.highlight-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-muted); }
.highlight-item svg { color: #34d399; flex-shrink: 0; }

/* ── 使用流程 ── */
.flow-section { position: relative; z-index: 1; padding: 80px 24px; max-width: 1000px; margin: 0 auto; }
.flow-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.flow-card { position: relative; padding: 24px 20px; background: rgba(255, 255, 255, 0.025); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 14px; }
.flow-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.flow-num { font-size: 28px; font-weight: 900; color: #e8b974; font-family: "SF Mono", monospace; text-shadow: 0 0 12px rgba(232, 185, 116, 0.3); }
.flow-icon { width: 36px; height: 36px; border-radius: 10px; background: rgba(232, 185, 116, 0.1); display: flex; align-items: center; justify-content: center; color: #e8b974; }
.flow-title { font-size: 15px; font-weight: 700; color: var(--text-primary); margin: 0 0 6px; }
.flow-desc { font-size: 11px; color: var(--text-muted); line-height: 1.6; margin: 0; }
.flow-arrow { position: absolute; right: -10px; top: 50%; transform: translateY(-50%); color: #334155; z-index: 2; }

/* ── 真实案例 ── */
.cases-section { position: relative; z-index: 1; padding: 80px 24px; max-width: 1000px; margin: 0 auto; }
.cases-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.case-card { padding: 22px; display: flex; flex-direction: column; gap: 10px; }
.case-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.case-scenario { font-size: 14px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.case-result-badge { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 5px; white-space: nowrap; flex-shrink: 0; }
.result-danger { background: rgba(251, 113, 133, 0.12); color: #fda4af; border: 1px solid rgba(251, 113, 133, 0.2); }
.result-warning { background: rgba(251, 191, 36, 0.12); color: #fde68a; border: 1px solid rgba(251, 191, 36, 0.2); }
.result-pass { background: rgba(52, 211, 153, 0.12); color: #6ee7b7; border: 1px solid rgba(52, 211, 153, 0.2); }
.case-profile { display: flex; align-items: center; gap: 4px; font-size: 11px; color: #f4d8a8; font-family: "SF Mono", monospace; }
.case-detail { font-size: 12px; color: var(--text-secondary); line-height: 1.7; margin: 0; font-weight: 300; }

/* ── FAQ ── */
.faq-section { position: relative; z-index: 1; padding: 80px 24px; max-width: 720px; margin: 0 auto; }
.faq-list { display: flex; flex-direction: column; gap: 10px; }
.faq-item { background: rgba(255, 255, 255, 0.025); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 12px; overflow: hidden; transition: all 0.2s; }
.faq-item.expanded { border-color: rgba(232, 185, 116, 0.15); background: rgba(232, 185, 116, 0.03); }
.faq-q { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; cursor: pointer; }
.faq-q-text { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.faq-toggle { font-size: 20px; color: #e8b974; transition: transform 0.3s; }
.faq-toggle.rotated { transform: rotate(45deg); }
.faq-a { padding: 0 20px 16px; }
.faq-a p { font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin: 0; font-weight: 300; }
.faq-expand-enter-active, .faq-expand-leave-active { transition: all 0.3s ease; }
.faq-expand-enter-from, .faq-expand-leave-to { opacity: 0; max-height: 0; }
.faq-expand-enter-to, .faq-expand-leave-from { opacity: 1; max-height: 200px; }

/* ── 最终 CTA ── */
.final-cta { position: relative; z-index: 1; padding: 60px 24px 80px; display: flex; justify-content: center; }
.cta-box { text-align: center; padding: 48px 40px; max-width: 560px; width: 100%; }
.cta-title { font-size: 28px; font-weight: 900; color: var(--text-primary); margin: 0 0 12px; letter-spacing: -1px; }
.cta-desc { font-size: 14px; color: var(--text-secondary); margin: 0 0 28px; font-weight: 300; }
.cta-btn-large { display: inline-flex; align-items: center; gap: 8px; padding: 16px 40px; background: linear-gradient(135deg, #e8b974, #d49a4e); border-radius: 14px; color: #fff; font-size: 17px; font-weight: 700; cursor: pointer; box-shadow: 0 8px 32px rgba(232, 185, 116, 0.35); transition: all 0.2s; }
.cta-btn-large:hover { box-shadow: 0 12px 44px rgba(232, 185, 116, 0.5); transform: translateY(-2px); }
.cta-btn-large:active { transform: scale(0.97); }

/* ── Footer ── */
.landing-footer { position: relative; z-index: 1; padding: 40px 24px; border-top: 1px solid rgba(255, 255, 255, 0.04); }
.footer-inner { max-width: 700px; margin: 0 auto; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 12px; }
.footer-brand { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--text-muted); }
.footer-wish { font-size: 16px; color: #f4d8a8; letter-spacing: 0.15em; text-shadow: 0 0 16px rgba(232, 185, 116, 0.2); }
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
