/**
 * 用户档案 Store — 本地缓存 + 后端 API 同步
 *
 * 策略:
 *   1. 默认空档案，用户必须先填写才能使用核心功能
 *   2. 优先从本地缓存 (localStorage) 恢复档案
 *   3. 用户编辑后同时写入本地缓存和后端 /api/profile
 *   4. 后端不可用时仅本地缓存，不影响主流程
 *
 * 数据收集字段:
 *   - 基础: 省份、总分、位次、选科组合、体检视力
 *   - 主科: 语文、数学、英语
 *   - 选科: 物理/化学/生物/历史/地理/政治（根据选科组合动态显示）
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { saveProfile, getProfile } from "../api";

export interface UserProfile {
  user_id: string;
  province: string;
  score: number | null;
  rank?: number | null;
  subjects?: string;
  // 主科成绩
  chinese_score?: number | null;
  math_score?: number | null;
  english_score?: number | null;
  // 选科成绩（物理/化学/生物/历史/地理/政治）
  physics_score?: number | null;
  chemistry_score?: number | null;
  biology_score?: number | null;
  history_score?: number | null;
  geography_score?: number | null;
  politics_score?: number | null;
  // 体检
  vision_status?: string;
  /** 索引签名：允许通过 string key 访问任意字段（用于动态字段绑定，如选科成绩） */
  [key: string]: number | string | null | undefined;
}

/** 创建空档案（所有字段为空，强制用户填写） */
function createEmptyProfile(userId: string): UserProfile {
  return {
    user_id: userId,
    province: "",
    score: null,
    rank: null,
    subjects: "",
    chinese_score: null,
    math_score: null,
    english_score: null,
    physics_score: null,
    chemistry_score: null,
    biology_score: null,
    history_score: null,
    geography_score: null,
    politics_score: null,
    vision_status: "",
  };
}

function generateUserId(): string {
  const stored = localStorage.getItem("gaokao_user_id");
  if (stored) return stored;
  const id = "user_" + Math.random().toString(36).slice(2, 10);
  localStorage.setItem("gaokao_user_id", id);
  return id;
}

export const useProfileStore = defineStore("profile", () => {
  const userId = ref(generateUserId());

  const profile = ref<UserProfile>(createEmptyProfile(userId.value));

  const syncStatus = ref<"idle" | "syncing" | "synced" | "error">("idle");

  /** 档案是否已完成基础填写（省份+分数+选科 为必填项） */
  const isProfileComplete = computed(() => {
    const p = profile.value;
    return !!(p.province && p.score && p.subjects);
  });

  /** 档案完成度百分比（用于引导提示） */
  const completionPercent = computed(() => {
    const p = profile.value;
    const fields = [
      p.province,
      p.score,
      p.subjects,
      p.rank,
      p.chinese_score,
      p.math_score,
      p.english_score,
      p.vision_status,
    ];
    const filled = fields.filter((v) => v !== null && v !== undefined && v !== "").length;
    return Math.round((filled / fields.length) * 100);
  });

  const summary = computed(() => {
    const p = profile.value;
    if (!isProfileComplete.value) return "档案未完善";
    const parts: string[] = [];
    if (p.score) parts.push(`${p.score}分`);
    if (p.province && p.subjects) {
      const subject = p.subjects.split(",")[0];
      const group = subject === "物理" ? "物理类" : subject === "历史" ? "历史类" : "";
      if (group) parts.push(`${p.province}${group}`);
    }
    if (p.english_score) parts.push(`英语${p.english_score}`);
    if (p.math_score) parts.push(`数学${p.math_score}`);
    return parts.join(" | ");
  });

  const loadFromCache = () => {
    try {
      const cached = localStorage.getItem("user_profile");
      if (cached) {
        const parsed = JSON.parse(cached);
        // 合并缓存数据，但保持空档案的字段结构（防止旧数据缺少新字段）
        profile.value = { ...createEmptyProfile(userId.value), ...parsed };
      }
    } catch {
      // ignore
    }
  };

  const saveToCache = () => {
    localStorage.setItem("user_profile", JSON.stringify(profile.value));
  };

  /** 同步到后端（静默失败，不影响本地） */
  const syncToBackend = async () => {
    syncStatus.value = "syncing";
    try {
      await saveProfile({ ...profile.value, user_id: userId.value });
      syncStatus.value = "synced";
    } catch {
      syncStatus.value = "error";
      // 后端不可用，静默失败——本地缓存仍有效
    }
  };

  const updateProfile = async (partial: Partial<UserProfile>) => {
    profile.value = { ...profile.value, ...partial };
    saveToCache();
    // 异步同步到后端，不阻塞 UI
    syncToBackend();
  };

  /** 启动时尝试从后端恢复档案 */
  const loadFromBackend = async () => {
    try {
      const remote = await getProfile(userId.value);
      if (remote && remote.province) {
        profile.value = { ...createEmptyProfile(userId.value), ...remote };
        saveToCache();
      }
    } catch {
      // 后端不可用，使用本地缓存
    }
  };

  return {
    userId,
    profile,
    summary,
    syncStatus,
    isProfileComplete,
    completionPercent,
    loadFromCache,
    updateProfile,
    syncToBackend,
    loadFromBackend,
  };
});
