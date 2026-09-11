-- ============================================================
-- 游戏人生（Game of Life）建表 SQL（随 M1 交付）
-- 目标数据库：MySQL 5.7+（SQLite 本地开发由 ORM 自动建表，结构一致）
-- 说明：与 app/models/__init__.py 中的 ORM 定义一一对应。
-- ============================================================

-- 1. 用户表
CREATE TABLE IF NOT EXISTS users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50)  NOT NULL UNIQUE,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 用户画像表（基础画像 + 初始属性快照 + 游戏化字段）
CREATE TABLE IF NOT EXISTS user_profiles (
    id                          INT AUTO_INCREMENT PRIMARY KEY,
    user_id                     INT  NOT NULL UNIQUE,
    basic_profile               JSON,
    initial_attributes_snapshot JSON,
    level                       INT  NOT NULL DEFAULT 1,
    exp                         DOUBLE NOT NULL DEFAULT 0.0,
    created_at                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_profile_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 属性定义 + 当前值
CREATE TABLE IF NOT EXISTS attributes (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    user_id       INT NOT NULL,
    name          VARCHAR(50) NOT NULL,
    description   TEXT,
    attr_type     VARCHAR(50) DEFAULT '',
    current_value DOUBLE NOT NULL DEFAULT 0.0,
    max_value     DOUBLE NOT NULL DEFAULT 100.0,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_attribute_user_name (user_id, name),
    CONSTRAINT fk_attr_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 属性值变更流水
CREATE TABLE IF NOT EXISTS attribute_history (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    attribute_id INT NOT NULL,
    event_id     INT,
    judgment_id  INT,
    delta        DOUBLE NOT NULL,
    value_after  DOUBLE NOT NULL,
    reason       TEXT,
    evidence     TEXT,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_history_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT fk_history_attr  FOREIGN KEY (attribute_id) REFERENCES attributes(id),
    CONSTRAINT fk_history_event FOREIGN KEY (event_id) REFERENCES events(id),
    CONSTRAINT fk_history_judge FOREIGN KEY (judgment_id) REFERENCES ai_judgments(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 事件表
CREATE TABLE IF NOT EXISTS events (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    event_type  VARCHAR(20) NOT NULL,          -- positive/negative/goal
    category    VARCHAR(50) DEFAULT '',
    source      VARCHAR(20) DEFAULT 'form',    -- form/journal
    title       VARCHAR(200) DEFAULT '',
    params      JSON,
    content     TEXT,
    occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_event_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. AI 判定记录
CREATE TABLE IF NOT EXISTS ai_judgments (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    event_id         INT NOT NULL,
    user_id          INT NOT NULL,
    suggested_changes JSON,                    -- AI 原始建议增减
    analysis         JSON,                     -- AI 分析过程（推理链路），v1.1 新增
    summary          TEXT,
    confidence       DOUBLE NOT NULL DEFAULT 0.0,
    confidence_reason TEXT,                     -- 置信度说明（v1.4：低置信度时 AI 给出不确定点）
    revision_notes   JSON,                      -- 本次修订说明（v1.6：重判时逐条说明改了什么）
    status           VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/confirmed/adjusted/rejected
    final_changes    JSON,                     -- 最终生效增减
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_judge_event FOREIGN KEY (event_id) REFERENCES events(id),
    CONSTRAINT fk_judge_user  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 判定审计日志
CREATE TABLE IF NOT EXISTS judgment_logs (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    judgment_id INT NOT NULL,
    user_id     INT NOT NULL,
    action      VARCHAR(30) NOT NULL,          -- create/confirm/supplement/dispute/rejudge
    detail      TEXT,
    payload     JSON,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_log_judge FOREIGN KEY (judgment_id) REFERENCES ai_judgments(id),
    CONSTRAINT fk_log_user  FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 目标表
CREATE TABLE IF NOT EXISTS goals (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    user_id           INT NOT NULL,
    description       TEXT,
    metric            VARCHAR(200) DEFAULT '',
    deadline          DATETIME,
    related_attribute VARCHAR(50) DEFAULT '',
    status            VARCHAR(20) NOT NULL DEFAULT 'active',  -- active/achieved/failed/cancelled
    reward            DOUBLE NOT NULL DEFAULT 2.0,
    penalty           DOUBLE NOT NULL DEFAULT -1.0,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_goal_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. 量化锚点库
CREATE TABLE IF NOT EXISTS anchors (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    description      TEXT,
    category         VARCHAR(50) DEFAULT '',
    target_attribute VARCHAR(50) DEFAULT '',
    base_value       DOUBLE NOT NULL DEFAULT 0.0,
    unit             VARCHAR(20) DEFAULT '',
    base_delta       DOUBLE NOT NULL DEFAULT 0.0,
    evidence         TEXT,
    is_builtin       TINYINT(1) NOT NULL DEFAULT 1,
    calibrated_value DOUBLE,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. 系统配置表
CREATE TABLE IF NOT EXISTS settings (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT NOT NULL,
    `key`      VARCHAR(100) NOT NULL,
    value      JSON,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_setting_user_key (user_id, `key`),
    CONSTRAINT fk_setting_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 内置量化锚点种子数据（PRD 6.4 节基准表）
-- 由应用启动时通过 anchor_service 自动写入（幂等），此处仅供文档/手动迁移参考。
-- ============================================================
-- INSERT INTO anchors (name, description, category, target_attribute,
--                      base_value, unit, base_delta, evidence, is_builtin) VALUES
--   ('中等强度有氧', '30 分钟慢跑/游泳/骑行', '锻炼', '体能', 30, '分钟', 1.0, 'ACSM 建议成人每周≥150 分钟中等强度有氧', 1),
--   ('深度专注学习', '1 小时无干扰专注学习', '学习', '智力', 60, '分钟', 1.0, '认知心理学：深度工作/心流促进长期记忆与理解', 1),
--   ('早睡充足睡眠', '23:00 前入睡且睡眠 7h+', '作息', '健康', 1, '次', 0.5, '睡眠研究：规律早睡与充足睡眠改善代谢与免疫', 1),
--   ('熬夜', '熬夜至凌晨 02:00', '作息', '健康', 1, '次', -0.5, '睡眠研究：长期熬夜损害认知与内分泌节律', 1),
--   ('目标达成', '目标到期且达成指标', '目标', '规划力', 1, '次', 2.0, '目标设定理论：达成反馈强化自我效能', 1),
--   ('目标未达成', '目标到期但未达成', '目标', '规划力', 1, '次', -1.0, '自我调节学习：未兑现计划反映规划执行力不足', 1);
