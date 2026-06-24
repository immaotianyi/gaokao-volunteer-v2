<!--
  pages/profile/profile.vue — 「我的」档案管理页 (V6)
  设计语言: Apple Vision 空间计算质感
  功能: 档案编辑 / 数据说明 / 免责声明 / 订单记录
-->
<script setup lang="ts">
import { ref, computed, watch } from "vue"
import { useRouter } from "vue-router"
import { useProfileStore, type UserProfile } from "../../stores/profile"
import { scoreToRank } from "../../api/index"
import { PROVINCE_OPTIONS, SUBJECT_PRESETS, getSubjectGroup, ELECTIVE_FIELD_MAP, DATA_COVERAGE, DISCLAIMER } from "../../constants/data"
import Icon from "../../components/Icon.vue"

const router = useRouter()
const profileStore = useProfileStore()

const editMode = ref(false)
const form = ref<UserProfile>({ ...profileStore.profile })
const rankLoading = ref(false)
const rankAutoMode = ref(true)

const provinceOptions = PROVINCE_OPTIONS
const subjectPresets = SUBJECT_PRESETS

const electiveFields = computed(() => {
  const subjects = form.value.subjects?.split(",").filter(Boolean) || []
  return subjects.map(s => ELECTIVE_FIELD_MAP[s]).filter(Boolean)
})

async function autoEstimateRank() {
  if (!rankAutoMode.value) return
  const score = form.value.score
  if (!score || score < 100 || score > 750) return
  if (form.value.province !== "广东") return
  rankLoading.value = true
  try {
    const subjectGroup = getSubjectGroup(form.value.subjects || "物理,化学,生物")
    const result = await scoreToRank(score, subjectGroup, 2025)
    form.value.rank = result.rank
  } catch { /* 静默失败 */ }
  finally { rankLoading.value = false }
}

let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch(() => form.value.score, () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => autoEstimateRank(), 500)
})

function toggleEdit() {
  if (editMode.value) {
    profileStore.updateProfile(form.value)
  } else {
    form.value = { ...profileStore.profile }
    if (rankAutoMode.value && form.value.score) autoEstimateRank()
  }
  editMode.value = !editMode.value
}

function cancelEdit() {
  form.value = { ...profileStore.profile }
  editMode.value = false
}

const syncLabel = computed(() => {
  const map: Record<string, string> = { idle: "未同步", syncing: "同步中...", synced: "已同步", error: "同步失败" }
  return map[profileStore.syncStatus] ?? "未同步"
})

// 免责声明
const disclaimerAccepted = ref(false)
</script>

<template>
  <div class="profile-shell">
    <!-- 背景光斑 -->
    <div class="bg-ambient">
      <div class="orb orb-1" />
      <div class="orb orb-2" />
    </div>

    <!-- Header -->
    <div class="profile-header">
      <div class="header-left-group">
        <div class="back-btn" @click="router.push('/workbench')">
          <Icon name="arrowLeft" :size="16" />
          <span>返回</span>
        </div>
        <span class="profile-title">我的</span>
      </div>
      <div class="sync-badge" :class="profileStore.syncStatus">
        <div class="sync-dot" />
        <span>{{ syncLabel }}</span>
      </div>
    </div>

    <!-- ── 档案卡片 ── -->
    <div class="section-card glass-card" :class="{ incomplete: !profileStore.isProfileComplete }">
      <div class="section-head">
        <span class="section-label">考生档案</span>
        <div class="edit-toggle" @click="toggleEdit">
          <span>{{ editMode ? '保存' : '编辑' }}</span>
        </div>
      </div>

      <!-- 分数 Hero -->
      <div class="score-hero" v-if="!editMode">
        <span class="score-value">{{ profileStore.profile.score || '---' }}</span>
        <span class="score-unit">分</span>
      </div>

      <!-- 编辑模式 — 分数 -->
      <div v-if="editMode" class="edit-score">
        <span class="edit-label">高考总分 <span class="required">*</span></span>
        <input
          v-model.number="form.score"
          type="number"
          class="edit-input score-input"
          placeholder="输入分数"
        />
      </div>

      <!-- 信息行 -->
      <div class="info-grid">
        <!-- 省份 -->
        <div class="info-item">
          <span class="info-label">省份 <span v-if="editMode" class="required">*</span></span>
          <select v-if="editMode" v-model="form.province" class="edit-picker">
            <option value="">选择省份</option>
            <option v-for="p in provinceOptions" :key="p" :value="p">{{ p }}</option>
          </select>
          <span v-else class="info-value">{{ profileStore.profile.province || '未设置' }}</span>
        </div>

        <!-- 选科 -->
        <div class="info-item">
          <span class="info-label">选科 <span v-if="editMode" class="required">*</span></span>
          <select v-if="editMode" v-model="form.subjects" class="edit-picker">
            <option value="">选择选科组合</option>
            <option v-for="s in subjectPresets" :key="s" :value="s">{{ s }}</option>
          </select>
          <span v-else class="info-value">{{ profileStore.profile.subjects || '未设置' }}</span>
        </div>

        <!-- 位次 -->
        <div class="info-item">
          <span class="info-label">
            省位次
            <span v-if="editMode" class="rank-auto-toggle" @click="rankAutoMode = !rankAutoMode">
              <span class="auto-dot" :class="{ active: rankAutoMode }"></span>
              {{ rankAutoMode ? '自动' : '手动' }}
            </span>
          </span>
          <input
            v-if="editMode"
            v-model.number="form.rank"
            type="number"
            class="edit-input"
            :class="{ 'rank-auto-input': rankAutoMode }"
            :readonly="rankAutoMode"
            placeholder="输入位次"
          />
          <span v-else class="info-value">{{ profileStore.profile.rank?.toLocaleString() ?? '未设置' }}</span>
          <span v-if="editMode && rankAutoMode && form.province === '广东'" class="rank-hint">根据2025年一分一段表自动推算</span>
          <span v-else-if="editMode && rankAutoMode && form.province && form.province !== '广东'" class="rank-hint warn">暂仅支持广东</span>
        </div>

        <!-- 语文 -->
        <div class="info-item">
          <span class="info-label">语文</span>
          <input
            v-if="editMode"
            v-model.number="form.chinese_score"
            type="number"
            class="edit-input"
            placeholder="输入分数"
          />
          <span v-else class="info-value">{{ profileStore.profile.chinese_score ?? '未设置' }}</span>
        </div>

        <!-- 数学 -->
        <div class="info-item">
          <span class="info-label">数学</span>
          <input
            v-if="editMode"
            v-model.number="form.math_score"
            type="number"
            class="edit-input"
            placeholder="输入分数"
          />
          <span v-else class="info-value">{{ profileStore.profile.math_score ?? '未设置' }}</span>
        </div>

        <!-- 英语 -->
        <div class="info-item">
          <span class="info-label">英语</span>
          <input
            v-if="editMode"
            v-model.number="form.english_score"
            type="number"
            class="edit-input"
            placeholder="输入分数"
          />
          <span v-else class="info-value">{{ profileStore.profile.english_score ?? '未设置' }}</span>
        </div>

        <!-- 选科成绩（动态） -->
        <template v-if="electiveFields.length || (!editMode && profileStore.profile.subjects)">
          <div v-for="subj in (editMode ? electiveFields : (profileStore.profile.subjects?.split(',').filter(Boolean).map(s => ELECTIVE_FIELD_MAP[s]).filter(Boolean) || []))" :key="subj.key" class="info-item">
            <span class="info-label">{{ subj.label }}</span>
            <input
              v-if="editMode"
              v-model.number="(form as Record<string, number | null | undefined>)[subj.key]"
              type="number"
              class="edit-input"
              placeholder="输入分数"
            />
            <span v-else class="info-value">{{ (profileStore.profile as Record<string, number | null | undefined>)[subj.key] ?? '未设置' }}</span>
          </div>
        </template>

        <!-- 视力 -->
        <div class="info-item">
          <span class="info-label">视力</span>
          <div v-if="editMode" class="vision-toggle">
            <div
              class="vision-opt"
              :class="{ active: form.vision_status === '正常' }"
              @click="form.vision_status = '正常'"
            >正常</div>
            <div
              class="vision-opt"
              :class="{ active: form.vision_status === '色弱' }"
              @click="form.vision_status = '色弱'"
            >色弱</div>
            <div
              class="vision-opt"
              :class="{ active: form.vision_status === '色盲' }"
              @click="form.vision_status = '色盲'"
            >色盲</div>
          </div>
          <span v-else class="info-value">{{ profileStore.profile.vision_status || '未设置' }}</span>
        </div>
      </div>

      <!-- 编辑取消按钮 -->
      <div v-if="editMode" class="edit-actions">
        <div class="cancel-btn" @click="cancelEdit">
          <span>取消</span>
        </div>
      </div>
    </div>

    <!-- ── 数据覆盖说明 ── -->
    <div class="section-card glass-card">
      <div class="section-head">
        <span class="section-label">数据覆盖</span>
      </div>
      <div class="coverage-content">
        <div class="coverage-stats">
          <div class="coverage-stat">
            <span class="coverage-value">{{ DATA_COVERAGE.schools }}</span>
            <span class="coverage-unit">所</span>
            <span class="coverage-desc">大学章程</span>
          </div>
          <div class="coverage-stat">
            <span class="coverage-value">{{ DATA_COVERAGE.plans.toLocaleString() }}</span>
            <span class="coverage-unit">条</span>
            <span class="coverage-desc">招生计划</span>
          </div>
          <div class="coverage-stat">
            <span class="coverage-value">{{ DATA_COVERAGE.provinces.length }}</span>
            <span class="coverage-unit">省</span>
            <span class="coverage-desc">数据覆盖</span>
          </div>
        </div>
        <div class="coverage-provinces">
          <span class="province-label">已覆盖省份:</span>
          <div class="province-tags">
            <span v-for="p in DATA_COVERAGE.provinces" :key="p" class="province-tag">{{ p }}</span>
          </div>
        </div>
        <p class="coverage-note">{{ DATA_COVERAGE.note }}</p>
      </div>
    </div>

    <!-- ── 免责声明 ── -->
    <div class="section-card glass-card">
      <div class="section-head">
        <span class="section-label">免责声明</span>
      </div>
      <div class="disclaimer-content">
        <span class="disclaimer-body">{{ DISCLAIMER.body }}</span>
        <div class="disclaimer-agree" @click="disclaimerAccepted = !disclaimerAccepted">
          <div class="agree-box" :class="{ checked: disclaimerAccepted }">
            <Icon v-if="disclaimerAccepted" name="check" :size="12" />
          </div>
          <span class="agree-label">我已阅读并理解上述声明</span>
        </div>
      </div>
    </div>

    <!-- ── 订单记录 ── -->
    <div class="section-card glass-card">
      <div class="section-head">
        <span class="section-label">订单记录</span>
      </div>
      <div class="order-empty">
        <span class="order-empty-text">暂无支付记录</span>
        <span class="order-empty-hint">支付解锁后此处将显示订单明细</span>
      </div>
    </div>

    <!-- ── 底部信息 ── -->
    <div class="profile-footer">
      <span class="footer-version">高考志愿狙击手 v0.8.0</span>
      <span class="footer-copy">© 2026 GAOKAO SNIPER</span>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════ Shell ═══════════ */
.profile-shell {
  min-height: 100vh;
  background: #020617;
  color: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "SF Pro Display", sans-serif;
  position: relative;
  padding-bottom: 40px;
}

/* ── 背景光斑 ── */
.bg-ambient {
  position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden;
}
.orb {
  position: absolute; border-radius: 50%; filter: blur(120px); opacity: 0.1;
}
.orb-1 { width: 400px; height: 400px; background: radial-gradient(circle, #38bdf8, transparent); top: -100px; right: -60px; }
.orb-2 { width: 300px; height: 300px; background: radial-gradient(circle, #818cf8, transparent); bottom: -60px; left: -40px; }

/* ── Glass Card ── */
.glass-card {
  background: rgba(255, 255, 255, 0.04);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-top: 1px solid rgba(255, 255, 255, 0.15);
  border-left: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.1);
  border-radius: 12px;
}

.section-card.incomplete { border-color: rgba(251, 191, 36, 0.2); }

/* ═══════════ Header ═══════════ */
.profile-header {
  position: relative; z-index: 1;
  display: flex; align-items: center; justify-content: space-between;
  padding: 30px 20px 16px;
}
.header-left-group { display: flex; align-items: center; gap: 16px; }
.back-btn { display: flex; align-items: center; gap: 4px; padding: 6px 14px; border-radius: 10px; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.08); color: #94a3b8; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
.back-btn:hover { background: rgba(255, 255, 255, 0.08); color: #e2e8f0; border-color: rgba(255, 255, 255, 0.15); }
.back-btn:active { background: rgba(255, 255, 255, 0.1); color: #e2e8f0; transform: scale(0.96); }
.profile-title {
  font-size: 28px; font-weight: 900; color: #f1f5f9; letter-spacing: -1px;
}
.sync-badge {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 12px; border-radius: 10px;
  font-size: 11px; font-weight: 600;
  background: rgba(255, 255, 255, 0.04); color: #64748b;
}
.sync-badge.synced { color: #86efac; }
.sync-badge.syncing { color: #7dd3fc; }
.sync-badge.error { color: #fda4af; }
.sync-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: #64748b;
}
.sync-badge.synced .sync-dot { background: #22c55e; }
.sync-badge.syncing .sync-dot { background: #38bdf8; animation: pulse 1s infinite; }
.sync-badge.error .sync-dot { background: #ef4444; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ═══════════ Section ═══════════ */
.section-card {
  position: relative; z-index: 1;
  margin: 0 16px 12px;
  padding: 20px;
}
.section-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 14px;
}
.section-label {
  font-size: 11px; font-weight: 700; color: #64748b;
  text-transform: uppercase; letter-spacing: 2px;
}
.edit-toggle {
  padding: 5px 14px; border-radius: 10px;
  font-size: 12px; font-weight: 600;
  background: rgba(56, 189, 248, 0.1);
  color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.2);
  cursor: pointer; transition: all 0.2s;
}
.edit-toggle:hover { background: rgba(56, 189, 248, 0.18); border-color: rgba(56, 189, 248, 0.35); }

/* ── Score Hero ── */
.score-hero {
  margin-bottom: 18px;
}
.score-value {
  font-size: 48px; font-weight: 200; color: #f1f5f9;
  line-height: 1; letter-spacing: -3px;
}
.score-unit {
  font-size: 16px; color: #64748b; margin-left: 4px;
}

/* ── 编辑模式 ── */
.edit-score { margin-bottom: 12px; }
.edit-label { font-size: 13px; color: #64748b; display: block; margin-bottom: 6px; }
.required { color: #fb7185; }
.score-input { font-size: 32px !important; font-weight: 200; }
.edit-input {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 7px; padding: 6px 10px;
  font-size: 13px; color: #f1f5f9; text-align: right;
}
.edit-input:focus { border-color: rgba(56, 189, 248, 0.4); }
.edit-picker {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 7px; padding: 6px 10px;
  font-size: 13px; color: #94a3b8; text-align: right;
}

/* ── Info Grid ── */
.info-grid {
  display: flex; flex-direction: column; gap: 10px;
}
.info-item {
  display: flex; justify-content: space-between; align-items: center;
  padding-bottom: 8px; border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}
.info-label { font-size: 13px; color: #64748b; display: flex; align-items: center; }
.info-value { font-size: 13px; color: #e2e8f0; font-weight: 600; }

/* ── Vision Toggle ── */
.vision-toggle { display: flex; gap: 4px; }
.vision-opt {
  padding: 5px 10px; border-radius: 7px;
  font-size: 12px; font-weight: 600;
  background: rgba(255, 255, 255, 0.04); color: #94a3b8;
}
.vision-opt.active {
  background: rgba(56, 189, 248, 0.15); color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.3);
}

/* ── Edit Actions ── */
.edit-actions { margin-top: 14px; }
.cancel-btn {
  padding: 8px 0; text-align: center; border-radius: 8px;
  background: rgba(255, 255, 255, 0.04); font-size: 13px; color: #94a3b8;
}

/* ═══════════ 数据覆盖说明 ═══════════ */
.coverage-content { padding: 4px 0; }
.coverage-stats { display: flex; gap: 12px; margin-bottom: 16px; }
.coverage-stat { flex: 1; text-align: center; padding: 16px 8px; background: rgba(255, 255, 255, 0.03); border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.05); }
.coverage-value { font-size: 28px; font-weight: 900; color: #f1f5f9; font-family: "SF Mono", monospace; display: block; line-height: 1; }
.coverage-unit { font-size: 12px; color: #38bdf8; font-weight: 600; }
.coverage-desc { font-size: 11px; color: #64748b; display: block; margin-top: 6px; }
.coverage-provinces { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.province-label { font-size: 12px; color: #64748b; }
.province-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.province-tag { font-size: 11px; font-weight: 600; padding: 3px 10px; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.15); border-radius: 12px; color: #7dd3fc; }
.coverage-note { font-size: 12px; color: #64748b; line-height: 1.7; margin: 0; }

/* ═══════════ 免责声明 ═══════════ */
.disclaimer-content {
  padding: 4px 0;
}
.disclaimer-body {
  font-size: 12px; color: #64748b; line-height: 1.8;
  display: block; margin-bottom: 12px;
}
.disclaimer-agree {
  display: flex; align-items: center; gap: 6px;
}
.agree-box {
  width: 18px; height: 18px; border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.agree-box.checked { background: #38bdf8; border-color: #38bdf8; }
.agree-label { font-size: 12px; color: #94a3b8; }

/* ═══════════ 订单记录 ═══════════ */
.order-empty {
  text-align: center; padding: 24px 0;
}
.order-empty-text {
  font-size: 14px; color: #94a3b8; display: block; margin-bottom: 4px;
}
.order-empty-hint {
  font-size: 11px; color: #475569;
}

/* ═══════════ Footer ═══════════ */
.profile-footer {
  position: relative; z-index: 1;
  text-align: center; padding: 20px 0;
}
.footer-version { font-size: 11px; color: #475569; display: block; }
.footer-copy { font-size: 10px; color: #334155; margin-top: 3px; display: block; }

/* ── 位次自动推算 ── */
.rank-auto-toggle { font-size: 10px; font-weight: 400; color: #64748b; cursor: pointer; margin-left: 6px; display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.03); }
.rank-auto-toggle:hover { color: #38bdf8; }
.auto-dot { width: 6px; height: 6px; border-radius: 50%; background: #475569; transition: all 0.2s; }
.auto-dot.active { background: #10b981; box-shadow: 0 0 6px rgba(16,185,129,0.5); }
.rank-auto-input { background: rgba(16,185,129,0.04) !important; border-color: rgba(16,185,129,0.15) !important; color: #6ee7b7 !important; }
.rank-hint { font-size: 10px; color: #10b981; display: block; margin-top: 2px; }
.rank-hint.warn { color: #f59e0b; }
</style>
