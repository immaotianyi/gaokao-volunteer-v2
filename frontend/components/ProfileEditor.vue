<!-- components/ProfileEditor.vue — 档案编辑弹窗（沉浸式，不跳页）-->
<script setup lang="ts">
import { ref, computed, watch } from "vue"
import { useProfileStore, type UserProfile } from "../stores/profile"
import { toast } from "../utils/toast"
import { scoreToRank } from "../api/index"
import { PROVINCE_OPTIONS, SUBJECT_PRESETS, getSubjectGroup, ELECTIVE_FIELD_MAP, DATA_COVERAGE } from "../constants/data"
import Icon from "./Icon.vue"

const emit = defineEmits<{ close: [] }>()
const profileStore = useProfileStore()

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
  const province = form.value.province
  const subjects = form.value.subjects || "物理,化学,生物"

  if (!score || score < 100 || score > 750) return
  if (province !== "广东") return

  rankLoading.value = true
  try {
    const subjectGroup = getSubjectGroup(subjects)
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
watch(() => form.value.subjects, () => {
  if (rankAutoMode.value && form.value.score) autoEstimateRank()
})

const validationError = computed(() => {
  if (!form.value.province) return "请选择省份"
  if (!form.value.score || form.value.score < 0 || form.value.score > 750) return "请输入有效高考分数（0-750）"
  if (!form.value.subjects) return "请选择选科组合"
  return ""
})

function save() {
  if (validationError.value) { toast.error(validationError.value); return }
  profileStore.updateProfile(form.value)
  toast.success("档案已更新")
  emit("close")
}

function cancel() {
  form.value = { ...profileStore.profile }
  emit("close")
}

function toggleRankMode() {
  rankAutoMode.value = !rankAutoMode.value
  if (rankAutoMode.value && form.value.score) autoEstimateRank()
}

/** Typed accessor for dynamic field binding — avoids `as any` in template */
const scoreFields = computed(() => form.value as Record<string, number | null | undefined>)
</script>

<template>
  <div class="editor-overlay" @click.self="cancel">
    <div class="editor-panel">
      <div class="editor-head">
        <span class="editor-title">编辑考生档案</span>
        <div class="editor-close" @click="cancel"><Icon name="close" :size="14" /></div>
      </div>

      <div class="editor-body">
        <!-- 总分 -->
        <div class="field-row">
          <label class="field-label">高考总分 <span class="required">*</span></label>
          <input v-model.number="form.score" type="number" class="field-input score-input" placeholder="输入分数（0-750）" />
        </div>

        <!-- 省份 + 选科 -->
        <div class="field-row-dual">
          <div class="field-half">
            <label class="field-label">省份 <span class="required">*</span></label>
            <select v-model="form.province" class="field-input">
              <option value="">选择省份</option>
              <option v-for="p in provinceOptions" :key="p" :value="p">{{ p }}</option>
            </select>
          </div>
          <div class="field-half">
            <label class="field-label">选科组合 <span class="required">*</span></label>
            <select v-model="form.subjects" class="field-input">
              <option value="">选择选科</option>
              <option v-for="s in subjectPresets" :key="s" :value="s">{{ s }}</option>
            </select>
          </div>
        </div>

        <!-- 位次 -->
        <div class="field-row">
          <label class="field-label">
            全省位次
            <span class="rank-auto-toggle" @click="toggleRankMode" :title="rankAutoMode ? '点击切换为手动输入' : '点击切换为自动推算'">
              <span class="auto-dot" :class="{ active: rankAutoMode }"></span>
              {{ rankAutoMode ? '自动推算' : '手动输入' }}
            </span>
          </label>
          <div class="rank-input-row">
            <input
              v-model.number="form.rank"
              type="number"
              class="field-input rank-field"
              placeholder="输入位次"
              :class="{ 'rank-auto': rankAutoMode, 'rank-loading': rankLoading }"
              :readonly="rankAutoMode"
            />
            <div v-if="rankLoading" class="rank-spinner"></div>
          </div>
          <span v-if="rankAutoMode && form.province === '广东'" class="rank-hint">根据2025年一分一段表自动推算</span>
          <span v-else-if="rankAutoMode && form.province && form.province !== '广东'" class="rank-hint warn">暂仅支持广东，请手动输入位次</span>
        </div>

        <!-- 主科成绩 -->
        <div class="section-divider">
          <span class="divider-text">主科成绩</span>
        </div>
        <div class="field-row-triple">
          <div class="field-third">
            <label class="field-label">语文</label>
            <input v-model.number="form.chinese_score" type="number" class="field-input" placeholder="分数" />
          </div>
          <div class="field-third">
            <label class="field-label">数学</label>
            <input v-model.number="form.math_score" type="number" class="field-input" placeholder="分数" />
          </div>
          <div class="field-third">
            <label class="field-label">英语</label>
            <input v-model.number="form.english_score" type="number" class="field-input" placeholder="分数" />
          </div>
        </div>

        <!-- 选科成绩（动态显示） -->
        <template v-if="electiveFields.length">
          <div class="section-divider">
            <span class="divider-text">选科成绩</span>
          </div>
          <div class="field-row-triple" :style="{ '--count': electiveFields.length } as any">
            <div v-for="subj in electiveFields" :key="subj.key" class="field-third">
              <label class="field-label">{{ subj.label }}</label>
              <input v-model.number="scoreFields[subj.key]" type="number" class="field-input" placeholder="分数" />
            </div>
          </div>
        </template>

        <!-- 视力 -->
        <div class="section-divider">
          <span class="divider-text">体检信息</span>
        </div>
        <div class="field-row">
          <label class="field-label">体检视力</label>
          <div class="vision-row">
            <div class="vision-opt" :class="{ active: form.vision_status === '正常' }" @click="form.vision_status = '正常'">正常</div>
            <div class="vision-opt" :class="{ active: form.vision_status === '色弱' }" @click="form.vision_status = '色弱'">色弱</div>
            <div class="vision-opt" :class="{ active: form.vision_status === '色盲' }" @click="form.vision_status = '色盲'">色盲</div>
          </div>
        </div>

        <!-- 数据收集说明 -->
        <div class="data-notice">
          <div class="notice-head">
            <span class="notice-icon">i</span>
            <span class="notice-title">数据说明</span>
          </div>
          <p class="notice-body">
            当前已收录 <strong>{{ DATA_COVERAGE.schools }}</strong> 所大学招生章程，招生计划覆盖
            <strong>{{ DATA_COVERAGE.provinces.join("、") }}</strong> 共 5 省。
          </p>
          <p class="notice-sub">{{ DATA_COVERAGE.note }}</p>
          <p class="notice-privacy">你的档案数据仅存储在浏览器本地，不会上传至第三方。后端同步功能即将上线。</p>
        </div>
      </div>

      <div class="editor-actions">
        <div class="btn-cancel" @click="cancel">取消</div>
        <div class="btn-save" :class="{ disabled: !!validationError }" @click="save">保存档案</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor-overlay { position: fixed; inset: 0; z-index: 150; display: flex; align-items: center; justify-content: center; background: rgba(2,6,23,0.6); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); padding: 16px; }
.editor-panel { width: 100%; max-width: 400px; max-height: 90vh; overflow-y: auto; background: rgba(15,23,42,0.95); backdrop-filter: blur(40px); -webkit-backdrop-filter: blur(40px); border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; padding: 24px; box-shadow: 0 24px 48px rgba(0,0,0,0.3); }
@media (min-width: 640px) { .editor-panel { padding: 32px; } }

.editor-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.editor-title { font-size: 18px; font-weight: 700; color: #f1f5f9; }
.editor-close { width: 28px; height: 28px; border-radius: 50%; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; cursor: pointer; color: #94a3b8; font-size: 14px; transition: all 0.2s; }
.editor-close:hover { background: rgba(255,255,255,0.12); }
.editor-close:active { transform: scale(0.9); }

.editor-body { display: flex; flex-direction: column; gap: 14px; }
.field-row { display: flex; flex-direction: column; gap: 4px; }
.field-row-dual { display: flex; gap: 10px; }
.field-half { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.field-row-triple { display: flex; gap: 8px; }
.field-third { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.field-label { font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 1px; display: flex; align-items: center; }
.required { color: #fb7185; margin-left: 2px; }
.field-input { background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 10px 12px; font-size: 14px; color: #e2e8f0; outline: none; box-sizing: border-box; width: 100%; transition: border-color 0.2s; }
.field-input:focus { border-color: rgba(56,189,248,0.4); }
.score-input { font-size: 28px; font-weight: 200; text-align: center; padding: 14px; }

/* ── 分隔线 ── */
.section-divider { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
.section-divider::before, .section-divider::after { content: ''; flex: 1; height: 1px; background: rgba(255,255,255,0.06); }
.divider-text { font-size: 10px; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 2px; }

.vision-row { display: flex; gap: 6px; }
.vision-opt { flex: 1; text-align: center; padding: 9px 0; border-radius: 8px; font-size: 13px; font-weight: 600; background: rgba(255,255,255,0.04); color: #94a3b8; cursor: pointer; transition: all 0.2s; }
.vision-opt:hover { background: rgba(56,189,248,0.08); color: #7dd3fc; }
.vision-opt.active { background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3); }

/* ── 位次自动推算 ── */
.rank-auto-toggle { font-size: 10px; font-weight: 400; text-transform: none; letter-spacing: 0; color: #64748b; cursor: pointer; margin-left: 6px; display: inline-flex; align-items: center; gap: 4px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.03); transition: all 0.2s; }
.rank-auto-toggle:hover { color: #38bdf8; background: rgba(56,189,248,0.08); }
.auto-dot { width: 6px; height: 6px; border-radius: 50%; background: #475569; transition: all 0.2s; }
.auto-dot.active { background: #10b981; box-shadow: 0 0 6px rgba(16,185,129,0.5); }
.rank-input-row { position: relative; }
.rank-field { transition: all 0.3s; }
.rank-field.rank-auto { background: rgba(16,185,129,0.04); border-color: rgba(16,185,129,0.15); color: #6ee7b7; }
.rank-field.rank-loading { opacity: 0.6; }
.rank-spinner { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); width: 16px; height: 16px; border: 2px solid rgba(56,189,248,0.2); border-top-color: #38bdf8; border-radius: 50%; animation: spin 0.6s linear infinite; }
@keyframes spin { to { transform: translateY(-50%) rotate(360deg); } }
.rank-hint { font-size: 10px; color: #10b981; margin-top: 2px; }
.rank-hint.warn { color: #f59e0b; }

/* ── 数据说明 ── */
.data-notice { margin-top: 4px; padding: 14px; background: rgba(56, 189, 248, 0.04); border: 1px solid rgba(56, 189, 248, 0.1); border-radius: 10px; }
.notice-head { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
.notice-icon { width: 16px; height: 16px; border-radius: 50%; background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-size: 10px; font-weight: 700; display: flex; align-items: center; justify-content: center; font-style: italic; }
.notice-title { font-size: 11px; font-weight: 700; color: #7dd3fc; text-transform: uppercase; letter-spacing: 1px; }
.notice-body { font-size: 12px; color: #94a3b8; line-height: 1.7; margin: 0 0 6px; }
.notice-body strong { color: #e2e8f0; font-weight: 700; }
.notice-sub { font-size: 11px; color: #64748b; line-height: 1.6; margin: 0 0 8px; }
.notice-privacy { font-size: 10px; color: #475569; line-height: 1.6; margin: 0; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.04); }

.editor-actions { display: flex; gap: 10px; margin-top: 20px; }
.btn-cancel { flex: 1; text-align: center; padding: 12px 0; border-radius: 10px; font-size: 14px; font-weight: 600; background: rgba(255,255,255,0.06); color: #94a3b8; cursor: pointer; transition: all 0.2s; }
.btn-cancel:hover { background: rgba(255,255,255,0.1); color: #e2e8f0; }
.btn-cancel:active { background: rgba(255,255,255,0.12); transform: scale(0.97); }
.btn-save { flex: 1.5; text-align: center; padding: 12px 0; border-radius: 10px; font-size: 14px; font-weight: 700; background: linear-gradient(135deg, #38bdf8, #818cf8); color: #fff; cursor: pointer; box-shadow: 0 8px 24px rgba(56,189,248,0.3); transition: all 0.2s; }
.btn-save:hover { box-shadow: 0 12px 32px rgba(56,189,248,0.45); transform: translateY(-1px); }
.btn-save:active { transform: scale(0.97); }
.btn-save.disabled { opacity: 0.4; pointer-events: none; }
</style>
