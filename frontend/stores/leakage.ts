/**
 * 捡漏雷达 Store (V2 — 六维评分 + 多维筛选)
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";

export interface LeakageOpportunity {
  university_name: string;
  major_name: string;
  group_code: string;
  plan_count: number;
  opportunity_type: string;  // 新增专业 | 扩招专业 | 中外合作
  reason: string;
  leakage_score?: number;         // V2: 0-100 评分
  score_breakdown?: string[];     // V2: 评分明细
  lowest_score_2025?: number | null;
  lowest_rank_2025?: number | null;
  school_type?: string | null;
  batch?: string | null;
  estimated_score?: number | null;     // V2: 预估分数线
  confidence_range?: number[] | null;  // V2: [low, high]
  estimation_source?: string | null;   // V2: 估值来源
  is_sino_foreign?: boolean;
  is_high_tuition?: boolean;
  is_new_campus?: boolean;
  is_first_batch?: boolean;
  subject_scarcity?: number | null;
  group_size?: number | null;
  tuition?: number | null;
  plan_count_prev?: number | null;
  // V3: Tavily 联网动态信息层
  live_latest_score?: string | null;
  live_employment?: string | null;
  live_news?: string | null;
  live_sources?: string[] | null;
  // V4: 数据可信度
  data_trust_level?: string | null;   // T1-T4
  data_trust_desc?: string | null;
}

export interface LeakageResult {
  province: string;
  subject_group: string;
  total: number;
  opportunities: LeakageOpportunity[];
  last_updated?: string | null;        // V2
  new_since_yesterday?: number;        // V2
  top_pick?: LeakageOpportunity | null; // V2
}

export const useLeakageStore = defineStore("leakage", () => {
  const result = ref<LeakageResult | null>(null);
  const loading = ref(false);
  const error = ref("");

  // V2 筛选参数
  const filterType = ref<string>("all");    // all | 新增专业 | 扩招专业 | 中外合作 | 新校区
  const filterTier = ref<string>("all");    // all | 985 | 211 | 双一流 | 省属重点
  const filterBatch = ref<string>("all");   // all | 本科批 | 提前批
  const sortBy = ref<string>("leakage_score"); // leakage_score | estimated_score | plan_count
  const scoreMin = ref<number>(300);
  const scoreMax = ref<number>(750);

  const unlocked = ref(false); // 是否已支付解锁
  const FREE_COUNT = 5;        // V2: 前5条免费

  const visibleItems = computed(() => {
    if (!result.value) return [];
    let items = [...result.value.opportunities];

    // 按类型筛选 (支持简写)
    const ft = filterType.value;
    if (ft === "新校区" || ft === "new_campus") {
      items = items.filter((i) => i.is_new_campus);
    } else if (ft === "new" || ft === "新增专业") {
      items = items.filter((i) => i.opportunity_type === "新增专业");
    } else if (ft === "expanded" || ft === "扩招专业") {
      items = items.filter((i) => i.opportunity_type === "扩招专业");
    } else if (ft === "中外合作") {
      items = items.filter((i) => i.opportunity_type === "中外合作");
    } else if (ft !== "all") {
      items = items.filter((i) => i.opportunity_type === ft);
    }

    // 按层次筛选
    if (filterTier.value !== "all") {
      items = items.filter((i) => i.school_type === filterTier.value);
    }

    // 按批次筛选
    if (filterBatch.value !== "all") {
      items = items.filter((i) => i.batch === filterBatch.value);
    }

    // 排序
    items.sort((a, b) => {
      if (sortBy.value === "leakage_score") return (b.leakage_score || 0) - (a.leakage_score || 0);
      if (sortBy.value === "estimated_score") return (b.estimated_score || 0) - (a.estimated_score || 0);
      if (sortBy.value === "plan_count") return (b.plan_count || 0) - (a.plan_count || 0);
      return 0;
    });

    return items;
  });

  const freeItems = computed(() => visibleItems.value.slice(0, FREE_COUNT));
  const lockedItems = computed(() => (unlocked.value ? [] : visibleItems.value.slice(FREE_COUNT)));
  const lockedCount = computed(() => lockedItems.value.length);

  const hasNewToday = computed(() => (result.value?.new_since_yesterday ?? 0) > 0);

  const setResult = (data: LeakageResult) => {
    result.value = data;
    unlocked.value = false;
  };

  const clear = () => {
    result.value = null;
    error.value = "";
    loading.value = false;
    unlocked.value = false;
  };

  // 兼容旧版 filter 字段
  const filter = computed({
    get: () => filterType.value,
    set: (val: string) => { filterType.value = val; },
  });

  return {
    result, loading, error,
    filter, filterType, filterTier, filterBatch, sortBy, scoreMin, scoreMax,
    unlocked, FREE_COUNT,
    visibleItems, freeItems, lockedItems, lockedCount, hasNewToday,
    setResult, clear,
  };
});
