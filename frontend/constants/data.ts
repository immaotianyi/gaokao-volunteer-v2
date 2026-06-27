/** 高考志愿狙击手 — 共享常量
 *
 *  版本号、数据覆盖、合规文案、定价等共享数据
 */

/** 数据覆盖范围 */
export const DATA_COVERAGE = {
  schools: 135,
  plans: 5261,
  provinces: ["广东", "河南", "山东", "四川", "江苏", "甘肃"] as readonly string[],
  note: "章程规则库覆盖全国 985/211/双一流高校，招生计划数据覆盖以上 6 省 2 科类。其他省份可正常使用探雷器和 AI 顾问，但部分功能精度可能受限。",
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

/** ───────────────────────────────────────────────
 *  诗句库 — 按场景分组，用于页面点缀（毛笔字呈现）
 *  选自唐宋诗词与先哲典籍，贴切填报志愿场景
 *  ─────────────────────────────────────────────── */
export interface PoetryItem {
  /** 主句 */
  line: string;
  /** 出处 */
  author: string;
  /** 下句（可选）*/
  sub?: string;
}

export const POETRY_LINES = {
  /** 欢迎/开场：志向与远望 */
  welcome: [
    { line: "长风破浪会有时", author: "李白·行路难", sub: "直挂云帆济沧海" },
    { line: "会当凌绝顶", author: "杜甫·望岳", sub: "一览众山小" },
  ],
  /** 等待/陪伴：耐心与积累 */
  waiting: [
    { line: "千淘万漉虽辛苦", author: "刘禹锡·浪淘沙", sub: "吹尽狂沙始到金" },
    { line: "不积跬步", author: "荀子·劝学", sub: "无以至千里" },
  ],
  /** 希望/转机：柳暗花明（适合捡漏雷达）*/
  hope: [
    { line: "山重水复疑无路", author: "陆游·游山西村", sub: "柳暗花明又一村" },
    { line: "行到水穷处", author: "王维·终南别业", sub: "坐看云起时" },
  ],
  /** 祝福/登科：金榜题名 */
  blessing: [
    { line: "春风得意马蹄疾", author: "孟郊·登科后", sub: "一日看尽长安花" },
  ],
  /** 安抚/坚定：莫愁前路、任尔风雨 */
  comfort: [
    { line: "莫愁前路无知己", author: "高适·别董大", sub: "天下谁人不识君" },
    { line: "千磨万击还坚劲", author: "郑燮·竹石", sub: "任尔东西南北风" },
  ],
  /** 沉稳/远见：不畏浮云 */
  steady: [
    { line: "不畏浮云遮望眼", author: "王安石·登飞来峰", sub: "自缘身在最高层" },
  ],
} as const;

/** 随机取一句诗（按场景），返回完整诗句对象 */
export function pickPoetry(scene: keyof typeof POETRY_LINES): PoetryItem {
  const pool = POETRY_LINES[scene] as unknown as PoetryItem[];
  return pool[Math.floor(Math.random() * pool.length)];
}

/** ───────────────────────────────────────────────
 *  人文陪伴文案 — 克制温暖，替代冷冰冰的技术文案
 *  ─────────────────────────────────────────────── */
export const COMFORT_TEXTS = {
  /** 品牌主名（弱化 SNIPER 狙击手，突出守护感）*/
  brandName: "志愿守护",
  brandTagline: "陪你把每一条志愿都核对清楚",
  brandFooterWish: "愿你心之所向，皆能如愿。",

  /** 空状态引导 */
  emptyProfileHint: "先把你的分数和选科填好，我们再开始。",
  emptyClipboardHint: "把你的志愿草表贴在这里，我们逐条核对。",
  emptyRadarHint: "填好分数和选科，我们来一起找找值得关注的院校。",

  /** 扫描过程 */
  scanningStart: "正在认真查阅每一所大学的招生章程…",
  scanningDone: "查完了，下面是我们发现的需要留意的地方。",
  scanningNoRisk: "每一条都查过了，没有发现显性限制，可以放心填报。",

  /** 风险等级 */
  riskPassLabel: "可以放心",
  riskWarningLabel: "需要留意",
  riskDangerLabel: "务必重视",

  /** 付费场景 */
  paymentTitle: "查看完整清单",
  paymentDesc: "还有 N 所院校的捡漏机会，每一所都经过算法筛选",
  paymentSuccess: "已解锁，祝你好运。",
  paymentHint: "解锁后可查看全部清单，7 天内有效",

  /** 网络/错误 */
  networkError: "网络不太稳，正在重试…",
  networkReconnect: "查询过程中遇到了点问题，可以重试一次。",
  saved: "档案已保存，可以开始填志愿了。",

  /** 陪伴/鼓励（散落各处的微文案）*/
  encourageStart: "别紧张，我们一步步来。",
  encourageWait: "稍等一下，章程比较多，我们逐一核对。",
  encourageDone: "都查完了，你可以放心往下走。",
} as const;

/** 探雷器「秉烛研卷」七阶段定义 — 替代原黑客风七幕
 *  保留仪式感，但画风转为"秉烛夜读招生章程"的东方人文意象
 */
export interface RitualStage {
  /** 阶段 key */
  key: string;
  /** 阶段名（毛笔字呈现）*/
  title: string;
  /** 一句话说明正在做什么（自然语言，非技术黑话）*/
  desc: string;
  /** 该阶段的诗句点缀 */
  poetry?: PoetryItem;
}

export const RITUAL_STAGES: RitualStage[] = [
  {
    key: "prepare",
    title: "研墨",
    desc: "准备好你的档案与志愿草表，我们要开始逐所核对了。",
    poetry: { line: "不积跬步", author: "荀子·劝学", sub: "无以至千里" },
  },
  {
    key: "read_profile",
    title: "展卷",
    desc: "正在读取你的省份、分数、选科和体检信息。",
  },
  {
    key: "parse_list",
    title: "列目",
    desc: "从你粘贴的草表里，识别出每一所大学和每一个专业。",
  },
  {
    key: "search_charter",
    title: "查典",
    desc: "逐所调取 2026 年招生章程，重点看体检、单科、语种、选科条款。",
    poetry: { line: "千淘万漉虽辛苦", author: "刘禹锡·浪淘沙", sub: "吹尽狂沙始到金" },
  },
  {
    key: "infer",
    title: "研判",
    desc: "把每条志愿和章程条款逐一对照，判断是否存在退档风险。",
  },
  {
    key: "report",
    title: "成文",
    desc: "整理成报告，标注风险等级与具体条款出处。",
    poetry: { line: "不畏浮云遮望眼", author: "王安石·登飞来峰", sub: "自缘身在最高层" },
  },
  {
    key: "done",
    title: "落幕",
    desc: "报告已成，下面是我们发现的需要留意的地方。",
    poetry: { line: "春风得意马蹄疾", author: "孟郊·登科后", sub: "一日看尽长安花" },
  },
];
