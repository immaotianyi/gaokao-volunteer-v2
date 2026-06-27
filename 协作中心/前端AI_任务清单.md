# 前端 AI 任务清单

> 派发时间：2026-06-27 10:01:20 | 派发人：审核员
> 任务数：1 项核心修复 + 2 项联调验证
> 项目根：`/Users/sanzhaibanniang/Claude/Projects/gaokao`

## 协作约定

1. 修复完成后在 `协作中心/反馈/` 新建 `YYYYMMDD_前端AI_完成说明.md`
2. 在 `协作中心/时间线.md` 追加 `[时间][前端AI] ✅ 完成 #x`
3. 验证：`cd frontend && npm run build` 必须 0 错误
4. 不影响既有"秉烛研卷"视觉主题（墨色底+烛光琥珀+毛笔标题+诗句点缀）
5. 联调验证项需等后端 AI 完成对应修复（#8/#9）后才能进行，关注时间线 ✅ 标记

---

## 核心任务 #11 — 消费热度 heat_* 字段（MINOR）

**文件**：`frontend/stores/leakage.ts`、`frontend/components/RadarCard.vue`

**问题**：后端 `run_leakage_radar` 为 top5 结果填充了 5 个热度字段，前端 `LeakageOpportunity` 接口未声明、`RadarCard.vue` 不渲染，数据被完全忽略，后端每次多查一次 Redis 却无人看。

**后端返回字段定义**（见 `backend/schemas.py` L161-L165）：
```python
heat_view_count: Optional[int]      # 累计查看次数
heat_watcher_count: Optional[int]   # 关注人数（去重）
heat_today_view: Optional[int]      # 今日查看次数
heat_level: Optional[str]           # cold/normal/hot/viral
heat_label: Optional[str]           # 少人关注/正常关注/热门机会/爆款机会
```

**修复提示词**：
```
阅读 frontend/stores/leakage.ts 的 LeakageOpportunity 接口定义（约 L8-L40）和
frontend/components/RadarCard.vue 全文。
要求：
1. 在 leakage.ts 的 LeakageOpportunity 接口中补 5 个可选字段（与后端 schemas.py L161-L165 一致）：
   heat_view_count?: number | null
   heat_watcher_count?: number | null
   heat_today_view?: number | null
   heat_level?: string | null       // 'cold' | 'normal' | 'hot' | 'viral'
   heat_label?: string | null
2. 在 RadarCard.vue 适当位置（建议卡片右上角或院校名旁）增加一个热度徽章：
   - 仅当 opportunity.heat_level 存在时渲染
   - 用 heat_label 作为文案（如"热门机会"）
   - 根据 heat_level 配色，遵循秉烛研卷主题：
     cold → 灰墨色（低饱和）
     normal → 默认琥珀
     hot → 加亮琥珀
     viral → 强调琥珀+微弱呼吸光效
   - 鼠标悬浮可显示 title="累计{heat_view_count}人查看 · 今日{heat_today_view}人 · {heat_watcher_count}人在盯"
   - 收藏数展示加 Math.max(0, n) 兜底（防 #5 后端修复前的负数）
3. 不要破坏现有卡片结构与动画
4. npm run build 必须 0 错误
```

**验收点**：捡漏雷达结果列表 top5 卡片显示热度徽章；build 0 错误。

---

## 联调验证 #8 — 选科成绩回显（待后端完成）

**前置条件**：时间线出现 `[后端AI] ✅ 完成 #8` 后进行。

**验证步骤**：
```
1. 启动后端（cd backend && uvicorn main:app --port 8000）
2. 启动前端（cd frontend && npm run dev）
3. 在"我的档案"页填写选科成绩（如物理 95、化学 88）
4. 刷新页面，确认选科成绩正确回显（未丢失）
5. 清浏览器 localStorage 后重新加载，确认从后端 GET 回显一致
6. 若回显正常，在时间线写 [前端AI] 🔍 #8 联调通过
7. 若丢失/为 null，在反馈/ 写失败说明并 @审核员
```

---

## 联调验证 #9 — career_risk/ai_risk 标签（待后端完成）

**前置条件**：时间线出现 `[后端AI] ✅ 完成 #9` 后进行。

**验证步骤**：
```
1. 确认后端 risk_checker 已透传 career_risk/ai_risk
2. 在志愿探雷器审查一组志愿（建议含就业风险/AI 替代风险敏感专业，如翻译、基础文职类）
3. 确认 RiskScanner.vue L651-L683 的"就业风险""AI替代风险"标签在 LLM 返回对应字段时正常显示
4. 无 LLM（mock 模式）时标签不显示（符合预期，不报错）
5. 通过则在时间线写 [前端AI] 🔍 #9 联调通过
```

---

## 兜底建议（可选，不强制）

针对 #5（收藏负数），在 RadarCard 展示任何收藏/关注数时统一加 `Math.max(0, value ?? 0)`，作为前端防御层。后端修复后此兜底无害保留。

---

## 完成后自检清单

- [ ] `cd frontend && npm run build` 0 错误 0 警告
- [ ] 浏览器控制台无报错
- [ ] 热度徽章在 top5 卡片可见且配色符合主题
- [ ] 在 `反馈/` 写完成说明，在 `时间线.md` 追加 ✅ 记录
