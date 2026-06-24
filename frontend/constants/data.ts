/** 高考志愿狙击手 — 共享常量
 *
 *  版本号、数据覆盖、合规文案、定价等共享数据
 */

/** 数据覆盖范围 */
export const DATA_COVERAGE = {
  schools: 135,
  plans: 5261,
  provinces: ["广东", "河南", "山东", "四川", "江苏"] as readonly string[],
  note: "章程规则库覆盖全国 985/211/双一流高校，招生计划数据覆盖以上 5 省 2 科类。其他省份可正常使用探雷器和 AI 顾问，但部分功能精度可能受限。",
} as const;

/** 合规免责声明（PRD §1 强制要求） */
export const DISCLAIMER = {
  body: "本工具数据来源于各省考试院与公开招生章程，受限于数据更新延迟与AI理解能力，本报告仅作为辅助筛查工具，不构成最终填报承诺，考生须最终核对官方《填报指南》与官网章程。",
  version: "v0.8.0",
  year: 2026,
} as const;

/** 省份列表 */
export const PROVINCE_OPTIONS = [
  "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江",
  "上海", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南",
  "湖北", "湖南", "广东", "广西", "海南", "重庆", "四川", "贵州",
  "云南", "西藏", "陕西", "甘肃", "青海", "宁夏", "新疆",
] as readonly string[];

/** 选科组合预设 */
export const SUBJECT_PRESETS = [
  "物理,化学,生物",
  "物理,化学,地理",
  "物理,生物,地理",
  "物理,政治,生物",
  "历史,政治,地理",
  "历史,政治,生物",
  "历史,地理,政治",
] as readonly string[];

/** 选科到科类的映射 */
export function getSubjectGroup(subjects: string): string {
  if (subjects.startsWith("物理")) return "物理类";
  if (subjects.startsWith("历史")) return "历史类";
  return "物理类";
}

/** 选科到成绩字段的映射 */
export const ELECTIVE_FIELD_MAP: Record<string, { label: string; key: string }> = {
  "物理": { label: "物理", key: "physics_score" },
  "化学": { label: "化学", key: "chemistry_score" },
  "生物": { label: "生物", key: "biology_score" },
  "历史": { label: "历史", key: "history_score" },
  "地理": { label: "地理", key: "geography_score" },
  "政治": { label: "政治", key: "politics_score" },
} as const;

/** 合规文案替换表 */
export const COMPLIANCE_TERMS: Record<string, string> = {
  "100%退档": "极高退档风险（触碰章程限制）",
  "天坑专业": "低偏好调剂专业",
  "绝对安全": "规则校验通过（未发现显性限制）",
  "保底录取": "过线概率大",
  "专家承诺": "算法测算结果仅供参考",
};
