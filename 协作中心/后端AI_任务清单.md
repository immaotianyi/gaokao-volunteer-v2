# 后端 AI 任务清单

> 派发时间：2026-06-27 10:01:20 | 派发人：审核员
> 更新时间：2026-06-27 10:12:00 | 审核员追加 #12（数据扩展前置阻塞）
> 任务数：11 项（2 critical / 7 major / 2 minor）
> 项目根：`/Users/sanzhaibanniang/Claude/Projects/gaokao`

## ⚠️ 数据扩展前置阻塞（必须先于爬虫完成）—【后端 AI 未拾取·仍待办 @11:08】

### 任务 #12 — score_rank 缺省份过滤，多省数据追加后位次串省（CRITICAL）❌未完成

**背景**：项目正在推进全国高考数据爬取（见 `backend/prompts/`，P0: 甘/豫/陕/川，P1: 皖/渝/闽/冀/鄂/湘/赣/辽）。所有 yifenyiduan_*.csv 是多省共享追加模式。**但 score_rank 服务完全不区分省份**，爬虫一旦追加新省数据，全站分数-位次转换立刻出错。

**文件**：`backend/services/score_rank.py`、`backend/routers/score_rank.py`、`backend/schemas.py`

**问题**：
1. `score_rank.py` `_load_table(year, subject_group)` 仅 `df[df["subject_group"] == subject_group]`，**无 province 过滤**；缓存 key 也只是 `(year, subject_group)`。
2. 当前 yifenyiduan_2026.csv 只有广东数据所以没事；一旦追加河南"物理类"行，广东用户查 600 分会把河南+广东物理类考生累计人数混算，位次错误。
3. `ScoreRankRequest`（schemas.py L279-L283）无 province 字段；`ScoreRankResponse`/`ScoreRangeResponse` 硬编码 `province: str = "广东"`；路由默认值也写死广东。

**修复提示词**：
```
阅读 backend/services/score_rank.py、backend/routers/score_rank.py、backend/schemas.py 的 ScoreRank* 模型。
当前 _load_table 只按 subject_group 过滤，多省数据会串。要求：
1. score_rank.py：
   - _load_table(year, subject_group, province) 增加 province 参数
   - 过滤改为 df[(df["subject_group"]==subject_group) & (df["province"]==province)]
   - batch 过滤（本科）保留
   - 缓存 key 改为 (year, subject_group, province)
   - score_to_rank / rank_to_score / get_score_range 全部增加 province 参数（默认 "广东" 保持兼容）
2. schemas.py：
   - ScoreRankRequest 增加 province: str = Field("广东", min_length=2, max_length=20)
   - ScoreRankResponse / ScoreRangeResponse 的 province 字段保留但改为接收实际值（不再硬编码）
3. routers/score_rank.py：
   - GET /convert、POST /convert、GET /range、GET /reverse 全部增加 province 查询参数（默认"广东"）
   - _do_convert 增加 province 参数透传
   - 响应的 province 用实际传入值
4. 验证：广东 600 分位次与改前一致；模拟追加一行河南物理类数据后，广东查询不受污染
必须在本任务完成、并确认广东数据回归无误后，再让爬虫脚本追加新省数据。
```

**验收点**：广东位次回归通过；新省数据追加后互不污染；`/api/score-rank/convert?score=600&province=广东` 与 `&province=河南` 返回各自正确位次。

---

## 协作约定

1. 修复完成后在 `协作中心/反馈/` 新建 `YYYYMMDD_后端AI_完成说明.md`，列出每个修复点：文件、行号、改法、是否重启验证。
2. 在 `协作中心/时间线.md` 追加一条 `[时间][后端AI] ✅ 完成 #x #y ...`。
3. 重启后端验证：`cd backend && uvicorn main:app --port 8000`（确保旧接口不破）。
4. 修复必须最小化，不引入未要求的重构。
5. #8/#9 修复后必须时间线标记，前端 AI 据此联调。

---

## 任务 #1 — 支付回调验签堵漏（CRITICAL）

**文件**：`backend/services/wechat_pay.py`、`backend/routers/payment.py`

**问题**：`_verify_signature`（约 L222-L225）在 `WECHAT_PLATFORM_CERT_PATH` 未配置时直接 `return True`，`/api/pay/notify` 据此跳过验签解密并解锁付费报告。生产环境漏配置即被伪造白嫖。

**修复提示词**：
```
阅读 backend/services/wechat_pay.py 的 _verify_signature 方法（约 L222-L225）和 is_configured 方法。
当前：WECHAT_PLATFORM_CERT_PATH 未配置时 _verify_signature 直接 return True。
要求改为：
1. 新增内部函数 _signature_strict() 返回布尔，表示"是否严格验签"：
   - 当环境变量 ENV == "prod" 时返回 True（必须验签）
   - 否则返回 False（开发/mock 模式允许跳过）
2. 在 is_configured() 返回 True 但 WECHAT_PLATFORM_CERT_PATH 为空时，
   在模块加载或 init 时打印一条 WARN 日志：
   "[WechatPay] ⚠ 已配置商户但缺少平台证书路径 WECHAT_PLATFORM_CERT_PATH，生产环境将拒绝回调"
3. 修改 payment.py 的 /api/pay/notify 处理：
   - 调用 _verify_signature 前先判断 _signature_strict()
   - 若 _signature_strict() 为 True 且验签失败 → 直接返回 HTTP 403，不解密不解锁
   - 若 _signature_strict() 为 False（开发模式）→ 维持现状（允许 mock 通过）
不要改动 mock 模式的现有行为，仅给生产模式加严格门禁。
```

**验收点**：mock 模式仍可解锁；模拟 ENV=prod 且证书缺失时 /api/pay/notify 返回 403。

---

## 任务 #2 — advisor 异步化 Tavily 调用（MAJOR）

**文件**：`backend/services/advisor.py`（约 L261）

**问题**：`maybe_live_search` 是 `async def`，却直接调同步 `tavily_search`（requests 库，阻塞最长 15s），卡死事件循环。

**修复提示词**：
```
阅读 backend/services/advisor.py 的 maybe_live_search 函数（约 L244-L269）。
当前 L261 形如：result = tavily_search(query + " 高考志愿 2026", 3)
要求：
1. 在文件顶部确认已 import asyncio（若无则添加）
2. 将该行改为：
   result = await asyncio.to_thread(tavily_search, query + " 高考志愿 2026", 3)
3. 检查 maybe_live_search 的所有调用方（chat / chat_stream）是否已正确 await，无需改动调用方
参考 backend/services/live_search.py 中 search_leakage_context（L515-L517）已用 asyncio.gather + to_thread 的正确写法。
不要改动其他逻辑。
```

**验收点**：触发顾问联网搜索时，并发请求不卡死。

---

## 任务 #3 — 邮件发送异步化（MAJOR）

**文件**：`backend/services/notification.py`（约 L287-L292）

**问题**：`send_daily_email` 是 `async def`，却用同步 `smtplib`（timeout=30），阻塞事件循环。

**修复提示词**：
```
阅读 backend/services/notification.py 的 send_daily_email 函数（约 L287-L292 及其内部 SMTP 逻辑）。
当前：在 async def 内直接用 smtplib.SMTP / starttls / login / send_message 同步调用。
要求：
1. 确认文件顶部 import asyncio
2. 将整段同步 SMTP 逻辑（连接+登录+发送+退出）抽到一个内部 def _smtp_send_sync(msg_str, config) 函数
3. 在 send_daily_email 中改为：
   await asyncio.to_thread(_smtp_send_sync, msg.as_string(), smtp_config)
4. 保留原有 try/except 与日志行为，仅做异步包装
不要引入新依赖（不要用 aiosmtplib）。
```

**验收点**：send_daily_email 不再阻塞事件循环；邮件功能行为不变。

---

## 任务 #4 — 统一差异追踪 key 格式（MAJOR）

**文件**：`backend/routers/leakage.py`（L198-L199 与 L276-L279）

**问题**：`_track_daily_diff` 在缓存命中路径用 `university_name+major_name`，新算路径用 `university_code_group_code_major_name`，导致 `new_since_yesterday` 失真。

**修复提示词**：
```
阅读 backend/routers/leakage.py 的 run_leakage_radar 函数。
定位两处构造 current_keys 的代码：
- 缓存命中路径（约 L198-L199）：
  set(o.get("unique_key", o.get("university_name","") + o.get("major_name","")) for o in data.get("opportunities", []))
- 新算路径（约 L276-L279）：
  uk = item.get("university_code", "") + "_" + item.get("group_code", "") + "_" + item.get("major_name", "")
注意：缓存里的 opportunities 来自 LeakageOpportunity schema，该 schema 无 unique_key/university_code/group_code 字段（见 schemas.py L127-L165），只有 university_name/major_name/group_code。
要求：
1. 在文件顶部新增一个公共函数：
   def _diff_key(university_name: str, major_name: str, group_code: str = "") -> str:
       return f"{university_name}|{major_name}|{group_code}"
2. 两处都改用该函数：
   - 缓存命中路径：set(_diff_key(o.get("university_name",""), o.get("major_name",""), o.get("group_code","")) for o in data.get("opportunities", []))
   - 新算路径：current_keys.add(_diff_key(item.get("university_name",""), item.get("major_name",""), item.get("group_code","")))
3. 确保两条路径 key 格式完全一致，与历史存储可比
不要改动 _track_daily_diff 本身。
```

**验收点**：缓存命中与新算两种路径下 new_since_yesterday 计数一致可比。

---

## 任务 #5 — heat_tracker 收藏数下限保护（MAJOR）

**文件**：`backend/services/heat_tracker.py`（L57-L60）

**问题**：Redis 路径 `unfav` 直接 `decr`，不存在 key 时 0→-1，与内存路径 `max(0,...)` 行为不一致，前端可能显示"收藏 -1"。

**修复提示词**：
```
阅读 backend/services/heat_tracker.py 的 track_event 函数 Redis 路径（约 L42-L68）。
当前 unfav 分支：pipe.decr(fav_key)
要求改为：用 Lua 脚本保证不为负，替换为：
  UNFAV_LUA = """
  local cur = tonumber(redis.call('GET', KEYS[1]) or '0')
  if cur > 0 then
      return redis.call('DECR', KEYS[1])
  else
      return 0
  end
  """
  pipe.eval(UNFAV_LUA, 1, fav_key)
注意 redis.asyncio 的 pipe.eval 签名：pipe.eval(script, numkeys, *keys_and_args)
确保内存路径（L88-L89 max(0,...)）保持不变。
```

**验收点**：连续 unfav 不存在的 key，fav_count 恒为 0 不为负。

---

## 任务 #6 — 热度追踪 Session 上下文管理（MAJOR）

**文件**：`backend/routers/leakage.py`（L696-L707）

**问题**：`db = SessionLocal()` → add → commit → close，close 未放 finally，异常时连接泄漏。

**修复提示词**：
```
阅读 backend/routers/leakage.py 的 track_heat 函数（约 L682-L714）。
当前持久化逻辑（约 L693-L707）：
  try:
      from database import SessionLocal
      from models import UserBehavior
      db = SessionLocal()
      db.add(UserBehavior(...))
      db.commit()
      db.close()
  except Exception:
      pass
要求改为 with 上下文管理器：
  try:
      from database import SessionLocal
      from models import UserBehavior
      with SessionLocal() as db:
          db.add(UserBehavior(...))
          db.commit()
  except Exception:
      pass
检查同文件内是否有其他类似 SessionLocal() 模式（如 heat_stats_overview），一并改为 with 上下文管理器。
确保 import 仍在函数内（不要提到模块顶部，避免循环导入）。
```

**验收点**：db.add/commit 抛异常时 session 正确关闭，无泄漏。

---

## 任务 #7 — enrollment_kb.query 返回 rules_text（MAJOR）

**文件**：`backend/services/enrollment_kb.py`（L129-L201）

**问题**：`query()` 返回 dict 缺 `rules_text`，违反约束；leakage.py customize（L541）等直读调用方有 KeyError 隐患。

**修复提示词**：
```
阅读 backend/services/enrollment_kb.py 的 query 方法（L108-L201）。
当前 result dict（L129-L140）字段：found/university/major/body_check/single_subject/language_restriction/subject_election/low_preference/notes/source
要求：
1. 在 result 初始化（L129-L140）中增加 "rules_text": ""
2. 在 query 方法的所有 return 出口前（L150 _apply_default_rules 路径、L201 末尾 return），
   补充：result["rules_text"] = self.get_rule_summary(university, major)
   注意 _apply_default_rules 可能返回新 dict，需在该方法内或调用后补 rules_text
3. 确认 get_rule_summary 方法存在且返回 str（参考 risk.py 路由已调用）
4. 不要改动路由层既有的 get_rule_summary 调用，保持兼容
验证：print(kb.query("暨南大学","临床医学")) 输出含非空 rules_text
```

**验收点**：`kb.query(...)` 返回 dict 含 `rules_text` 字符串字段。

---

## 任务 #8 — 补齐选科成绩字段（MAJOR，触发前端联调）

**文件**：`backend/schemas.py`（L13-L22）、`backend/models.py`（L10-L22）

**问题**：前端 `saveProfile` 发送 physics_score 等 6 字段，后端 schema/ORM 无定义，Pydantic 静默丢弃。

**修复提示词**：
```
阅读 backend/schemas.py 的 UserProfileBase（L13-L22）和 backend/models.py 的 UserProfile ORM（约 L10-L22）。
前端 frontend/stores/profile.ts L30-L35 已发送这 6 个字段：
  physics_score, chemistry_score, biology_score, history_score, geography_score, politics_score
要求：
1. 在 schemas.py 的 UserProfileBase 中（chinese_score 之后）补 6 个字段：
   physics_score: Optional[int] = Field(None, ge=0, le=100, description="物理成绩")
   chemistry_score: Optional[int] = Field(None, ge=0, le=100, description="化学成绩")
   biology_score: Optional[int] = Field(None, ge=0, le=100, description="生物成绩")
   history_score: Optional[int] = Field(None, ge=0, le=100, description="历史成绩")
   geography_score: Optional[int] = Field(None, ge=0, le=100, description="地理成绩")
   politics_score: Optional[int] = Field(None, ge=0, le=100, description="政治成绩")
   （注意：广东新高考选科单科满分 100，不是 150）
2. 在 models.py 的 UserProfile ORM 中补对应 6 列：
   physics_score = Column(Integer, nullable=True)
   ... 同理其余 5 个
3. 由于 SQLite 已建表，需在 main.py lifespan 的 Base.metadata.create_all 之外，
   用 alembic 或手动 ALTER TABLE 补列。简化做法：在数据库初始化处加一段
   "ALTER TABLE user_profiles ADD COLUMN physics_score INTEGER" 的 try/except（列已存在则忽略）
   参考 backend/scripts/ 下是否有现成迁移脚本风格
4. 验证：POST /api/profile 带 physics_score=95 能入库并 GET 回显
完成后在时间线写 ✅ 标记，触发前端 AI 联调验证回显。
```

**验收点**：profile 入库/回显含 6 字段；risk_checker 可读取（如未来需要单科门槛判断）。

---

## 任务 #9 — 补齐 career_risk/ai_risk 字段（MAJOR，触发前端联调）

**文件**：`backend/schemas.py`（L193-L198）、`backend/services/risk_checker.py`（L336-L340）、`backend/services/risk_agent.py`

**问题**：前端 RiskScanner.vue 渲染 career_risk/ai_risk 标签，后端 RiskCheckItem 无此字段，risk_checker 解析时丢弃，audit_prompts.py 却要求 LLM 输出。

**修复提示词**：
```
阅读：
- backend/schemas.py 的 RiskCheckItem（L193-L198）：当前仅 status/reason/matched_clause
- backend/services/risk_checker.py 的 _call_deepseek 解析（约 L326-L340）
- backend/services/risk_agent.py 的 _judge / parse_response
- backend/services/audit_prompts.py L84-L85：提示词已要求输出 career_risk / ai_risk
要求：
1. schemas.py 的 RiskCheckItem 在 matched_clause 之后补：
   career_risk: Optional[str] = Field(None, description="就业风险提示")
   ai_risk: Optional[str] = Field(None, description="AI替代风险提示")
2. risk_checker.py 解析 LLM 返回 dict 时（约 L336-L340），在构造返回 dict 时追加：
   career_risk=result.get("career_risk"),
   ai_risk=result.get("ai_risk"),
3. risk_agent.py 的 _judge / parse_response 同步透传这两个字段（若 LLM/Agent 返回了）
4. Mock 路径可不填（保持 None，前端 falsy 不渲染标签，符合预期）
完成后在时间线写 ✅ 标记，触发前端 AI 联调验证标签生效。
```

**验收点**：真实 LLM 返回 career_risk/ai_risk 时，前端标签正常显示。

---

## 任务 #10 — risk_agent API key 兼容（MINOR）

**文件**：`backend/routers/risk_agent.py`（L216 与 L271）

**问题**：仅检查 `LLM_API_KEY`，遗漏 `DEEPSEEK_API_KEY`，只配后者时 Agent 误退 Mock。

**修复提示词**：
```
阅读 backend/routers/risk_agent.py 的 L216 与 L271 附近的 provider 判断逻辑。
当前形如：if provider in ("openai","deepseek") and not _os.getenv("LLM_API_KEY"):
参考 backend/services/advisor.py L53 的写法：os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
要求：将两处的判断改为：
  not (_os.getenv("LLM_API_KEY") or _os.getenv("DEEPSEEK_API_KEY"))
确保只配 DEEPSEEK_API_KEY 时 V4 Agent 走真实 LLM 而非 Mock。
```

**验收点**：仅配 DEEPSEEK_API_KEY 时 Agent 不退 Mock。

---

## 完成后自检清单

- [ ] `cd backend && python -c "import main"` 无 import 错误
- [ ] `uvicorn main:app --port 8000` 启动无异常
- [ ] `curl http://localhost:8000/health` 返回 ok
- [ ] `curl -X POST http://localhost:8000/api/leakage-radar -H "Content-Type: application/json" -d '{"province":"广东","subject_group":"物理类","user_score":565}'` 返回正常
- [ ] 在 `反馈/` 写完成说明，在 `时间线.md` 追加 ✅ 记录
