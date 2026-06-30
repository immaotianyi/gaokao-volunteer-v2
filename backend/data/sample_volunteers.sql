-- =============================================================================
-- 高考志愿狙击手 · 模拟数据 INSERT (3 组典型场景)
-- 生成日期: 2026-06-20
-- 用法: 连接数据库后直接执行，或通过 seed_db.py 导入
-- =============================================================================

-- ── 场景一: 广东物理类 565 分 · 色弱 ──
INSERT OR REPLACE INTO user_profiles (user_id, province, score, rank, subjects, chinese_score, math_score, english_score, physics_score, chemistry_score, biology_score, vision_status)
VALUES ('user_demo_01', '广东', 565, 53200, '物理,化学,生物', 112, 105, 92, 78, 72, 85, '色弱');

-- ── 场景二: 河南历史类 555 分 · 数学短板 ──
INSERT OR REPLACE INTO user_profiles (user_id, province, score, rank, subjects, chinese_score, math_score, english_score, history_score, politics_score, geography_score, vision_status)
VALUES ('user_demo_02', '河南', 555, 48600, '历史,政治,地理', 118, 86, 108, 82, 78, 85, '正常');

-- ── 场景三: 山东物理类 580 分 · 全绿 ──
INSERT OR REPLACE INTO user_profiles (user_id, province, score, rank, subjects, chinese_score, math_score, english_score, physics_score, chemistry_score, biology_score, vision_status)
VALUES ('user_demo_03', '山东', 580, 37800, '物理,化学,生物', 108, 118, 115, 82, 79, 88, '正常');
