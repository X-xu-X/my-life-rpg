# 修复计划 v1.13.1 —— v1.13 审查发现的阻断项

> **决策来源**：2026-11-17 对 v1.13 六个代码 commit（`808fe9c`→`aa2ad65`）的逐行审查
> **代码基线**：HEAD `f779065`（v1.13 六批代码 + `f779065` 文档回写，共 **11 个 commit 未推送**）
> **前置文档**：`docs/DEV_PLAN_v1.13.md`（六批全部落地）
> **交付方式**：分批实现，**一批一个 commit**，只 commit 不 push

本轮**不改玩法、不加功能**，只修 v1.13 自己引入的缺陷，以及补上会让这版上线即挂的迁移缺口。

**当前状态**：v1.13 六批代码与文档回写全部在本地，**`main` 领先 `origin/main` 11 个 commit，尚未推送、尚未发布**（线上仍跑 `3fa0de7` / v1.12，库 head 仍是 `b025_daily_use`）。所以 P0-1 还没造成线上事故，但也意味着**只要按现有链路发一次，商店就会 500**。本轮必须先合并修复再发。

---

## 〇、问题清单

| 编号 | 级别 | 一句话 | 位置 | 不修的后果 |
|---|---|---|---|---|
| **P0-1** | 阻断 | 云端没有 `pricing_mode` 的 alembic 迁移 | `app/models/__init__.py:433` / `alembic/versions/` 止于 `b025` | 部署后 `/api/shop/items` 500，**商店整页打不开** |
| **P0-2** | 阻断 | 计时页 CSS 少一个花括号，整段被吞 | `frontend/src/daily-use.css:52` | 圆环、居中卡、大字时间**全部不生效**，视觉同 v1.12 |
| **P1-1** | 高 | 新旧两个定价开关已脱钩 | `app/routers/shop.py:62` vs `app/services/pricing_checks.py:34` | 调旧接口关不掉自动定价，或开了没反应 |
| **P1-2** | 高 | 「退回并冻结」把理由写脏 | `app/routers/shop.py:56` | 理由里留 48、界面显示 30，正是 F11 要消灭的矛盾 |
| **P1-3** | 高 | 分析页每条币数与实际入账不一致 | `frontend/src/components/FactAnalysis.vue:47` | 同卡上「12 币」和「本项新增 0 币」并存 |
| **P1-4** | 高 | 发布脚本硬编码 `b025_daily_use` | `ops/` 5 处 | 带迁移的发布会被自己的断言拒掉 |
| **P2-1** | 中 | `set_pricing_mode`/`rollback_price` 未走 receipts | `app/routers/shop.py:34,47` | 重复点击 409，与同类接口语义不一 |
| **P2-2** | 中 | 两个接口返回的 `redeemed_count` 恒 0 | `app/routers/shop.py:44,58` | 已兑完的券切组后短暂回到「只用这一次」列表 |
| **P2-3** | 中 | 409 文案还写「判档」 | `app/services/fact_analysis.py:201` | 用户看到已不存在概念 |
| **P2-4** | 中 | 「今日已得 N 币」只统计手账那一块 | `app/routers/trial.py:26` | 低报：漏掉首记 3 币、挑战、成就 |
| **P2-5** | 中 | 公安备案图标是自绘的圆+五角星 | `frontend/src/components/SiteFooter.vue:9` | 大概率被要求换成备案系统官方图 |
| **P2-6** | 低 | `permission()` 已是死代码 | `frontend/src/components/RewardShop.vue:34` | 留着会误导后来的人 |
| **P3-1** | 低 | 3 个既有测试与实现脱节 | `tests/test_release_readiness.py` | 永远不能「全绿」，真问题会被淹 |

**P3-1 的定性**：这 3 项在未改动的 `3fa0de7` 基线上同样失败，**不是 v1.13 引入的**，但既然查清了根因，顺手修掉，别一直挡着「全绿」。

---

## 一、总原则

继承 `DEV_PLAN_v1.13.md` 六条，本轮**追加三条**：

1. **【新增】改 CSS 必须起本地服务截图核对。** `vite build` 不校验 CSS 语法，本次 P0-2 就是「构建通过但样式全废」。验收标准是**看到图**，不是构建成功。
2. **【新增】云端 schema 变更必须写 alembic 修订。** `migrate_schema()` 只在 `settings.cloud == False` 的分支里跑（`app/main.py:120`），云模式校验完 `alembic_version == heads` 就在 `:116` 直接 `return`。**`migrate_schema` 对云端一行都不生效**——这是 v1.13 文档漏写的，也是 P0-1 的根因。
3. **【新增】PG 与 SQLite 的方言差异要显式处理。** 布尔列回填不能写 `= 1`，PG 拒绝 `boolean = integer`（SQLite 宽容）。统一写 `IS TRUE`。

---

## 二、批次划分

依赖：**G 必须最先**（其余各批都要在能跑起来的库上验证）→ H → I → J → K → L。
G/H 是「不改就发不出去」；I/J 是「发出去会出错」；K/L 是清理。

---

### 批次 G · 补齐云端迁移 + 发布链（P0-1 + P1-4）

**目标**：让 `alembic upgrade head` 能把库从 `b025` 带到新 schema，并让发布脚本认识新 head。

**涉及文件**

- `alembic/versions/b026_pricing_mode.py`（新建）
- `alembic/versions/b027_suppressed_lines.py`（新建）
- `app/database.py:79-83`（回填语句方言）
- `ops/cloud_update_snapshot.py:35`
- `ops/update-public.sh:2,37,67,114,152`
- `ops/rehearse_public_update.py:5,29`（仅注释）

**具体改法**

1. **`b026_pricing_mode.py`**

   ```python
   """Shop item pricing mode (once / recurring)."""
   from alembic import op
   import sqlalchemy as sa
   revision='b026_pricing_mode'
   down_revision='b025_daily_use'
   branch_labels=None
   depends_on=None


   def upgrade():
       op.add_column('shop_items',sa.Column('pricing_mode',sa.String(10),nullable=False,server_default='once'))
       # 旧开关回填：auto_pricing 为真的商品继续按「常用券」重估，其余落 once
       op.execute("UPDATE shop_items SET pricing_mode='recurring' WHERE auto_pricing IS TRUE")


   def downgrade():
       raise RuntimeError('价格历史与既定定价方式不自动回退，请从升级前备份隔离恢复。')
   ```

   - `server_default='once'` 让老行在加列瞬间就非空，避免 `NOT NULL` 违约；
   - 回填**必须在 `add_column` 之后、同一次 upgrade 里**做，否则老数据的 `pricing_mode` 全是 `once`，原本天天重估的商品会静默停掉。

2. **`b027_suppressed_lines.py`**

   ```python
   """Experience preference: suppressed tip lines."""
   from alembic import op
   import sqlalchemy as sa
   revision='b027_suppressed_lines'
   down_revision='b026_pricing_mode'
   branch_labels=None
   depends_on=None


   def upgrade():
       op.add_column('experience_preferences',sa.Column('suppressed_lines',sa.JSON(),nullable=True))


   def downgrade():
       raise RuntimeError('用户已关闭的提示行不自动回退，请从升级前备份隔离恢复。')
   ```

   - **不给 `server_default`**：模型是 `nullable=True`，老行留 `NULL`，读取处一律 `or []`（`app/models/daily_use.py:26` 的注释已写明这个约定）；
   - 这是**遗留老债**，不是 v1.13 引入的：`experience_preferences` 由 `b025` 建表时漏了这一列，本地 SQLite 靠 `migrate_schema` 补上，云端一直没有。顺手一起补，否则这次要发两轮。

3. **`app/database.py:83`**：`WHERE auto_pricing = 1` → `WHERE auto_pricing IS TRUE`。
   这段在云端不会执行（云模式不走 `migrate_schema`），但本地若切 PG 会直接抛 `UndefinedFunction`。改掉，别留一颗雷。

4. **`ops/` 的 5 处硬编码**。当前脚本断言「head 必须是 `b025_daily_use`」，迁移一上，**正确部署会被自己判为失败**。

   | 位置 | 现状 | 改成 |
   |---|---|---|
   | `cloud_update_snapshot.py:35` | `if heads != ['b025_daily_use']` | `if heads != expected_heads:`，`expected_heads` 由 `alembic heads` 运行时读取 |
   | `update-public.sh:37` | `if [[ "$head" = b025_daily_use ]]` | 同上的动态值；**回滚语义要跟着改，见下** |
   | `update-public.sh:67` | `assert ... r['head']==['b025_daily_use']` | 比对上一步读到的期望 head |
   | `update-public.sh:114` | `assert r['head']==['b025_daily_use']` | 同上 |
   | `update-public.sh:152` | `'database_head':'b025_daily_use'` | 写入实际 head |

   **不要改成「顺手把常量写成 `b027_suppressed_lines`」**——下一版又要改一遍，跟今天同一个坑。统一改成从 `alembic/versions/` 现算，或从 `RELEASE_MANIFEST.json` 里带的 head 读。

5. **`update-public.sh` 的回滚语义必须显式改写（这是 P1-4 真正的难点）**

   现在的失败处理是：head 还是 `b025` → 停新服务、起旧镜像；head 变了 → `DATABASE_HEAD_CHANGED: automatic rollback refused`。
   这条**不能简单地「放宽成新 head 也允许」**：schema 已经加了列、回填过数据，旧镜像能跑（多一列不影响 SELECT），但**逻辑上已经不是同一个库**，自动回滚会掩盖问题。

   本批的处理：
   - 迁移作为**独立的前置步骤**执行（在停写窗口内、备份之后、起新镜像之前），不进 `update-public.sh` 的自动流程；
   - 迁移失败 → 全部停止，用备份恢复，**不起新镜像、不切流量**；
   - 迁移成功但新镜像启动失败 → 允许回起旧镜像（旧代码不读 `pricing_mode`，多一列无害），但必须**在输出里显式打 `SCHEMA_AHEAD_OF_CODE`**，让人知道回滚后库是新 schema。
   - 这三条要写成脚本里的注释和输出文案，不能留在口头。

   **这一条涉及发布流程，属于「先说明做法再确认」的范围。**本批只做到「迁移文件 + 脚本断言动态化 + 回滚语义写成注释」，**真跑一次带迁移的发布，要等用户点头**。

**验收**

- `alembic heads` 只输出**一个** head：`b027_suppressed_lines`
- 在一个从 `b025` 复制出来的库上跑 `alembic upgrade head`，然后 `psql -c "\d shop_items"` 能看到 `pricing_mode`，`\d experience_preferences` 能看到 `suppressed_lines`
- 同库上确认回填：原本 `auto_pricing=true` 的商品 `pricing_mode='recurring'`，其余 `'once'`
- 本地 SQLite（非云模式）启动一次，`migrate_schema` 不报错，`shop_items` 与 `experience_preferences` 列齐全
- `grep -rn "b025_daily_use" ops/` 只剩注释里的历史说明，没有断言

**commit**：`fix(部署): 补 pricing_mode 与 suppressed_lines 迁移并去掉 head 硬编码`

---

### 批次 H · 计时页 CSS 修复（P0-2）

**目标**：让计时页真的变成 demo 那一屏。

**现状（原文）**

```css
.timer-ring{--pct:0;width:clamp(215px,52vw,238px);aspect-ratio:1;margin:18px auto;border-radius:50
/* v1.13 TM：计时页居中卡 + 圆环（只影响外观） */
.timer-card{max-width:720px;margin-inline:auto;text-align:center}
...
```

第 52 行 `.timer-ring` 的声明块**没有 `}`**，紧接着第 53 行起整段又被重复了一遍。浏览器的处理是从这里开始把后续内容全当一个未闭合块吞掉，于是 `.timer-card` / `.timer-head` / `.timer-quota` / `.timer-ring` / `.timer-ring-inner` / `.timer-used` **全部失效**。

实测：`{` 134 个、`}` 133 个；`.timer-ring{` 出现 **2** 次。

**涉及文件**：`frontend/src/daily-use.css:48-65`（第 45-46 行是 F13 的 `.reward-group-title`，**不在这批范围**，别一起删）

**模板侧是好的，不要动 `.vue`**：`TimerView.vue:34` 已经有 `.timer-card` / `.timer-head` / `.timer-quota` / `.timer-ring`（`:style="{'--pct': ringPct}"`）/ `.timer-ring-inner` / `.timer-used` 的完整结构，`ringPct` 是 `computed`，按已过时长算百分比。**本批只改 CSS 一个文件**。

**具体改法**

1. 删掉第 48-52 行那半段（含第 48 行的重复注释、49-51 行的三条规则、52 行未闭合的 `.timer-ring`），**保留第 53 行起完整的那一份**；
2. 完整那份里的注释保留一条即可；
3. 改完自查花括号配平与选择器去重（命令见验收）。

**验收（必须看图，不接受「构建通过」）**

```bash
cd my-life-rpg && ./.venv/Scripts/python.exe -c "
s=open('frontend/src/daily-use.css',encoding='utf-8').read()
assert s.count('{')==s.count('}'), (s.count('{'),s.count('}'))
assert s.count('.timer-ring{')==1, s.count('.timer-ring{')
print('css ok')"
```

然后起后端 + `npm run dev`，打开计时页截图（Edge headless，`--window-size=1180,900`），逐项确认：
- 卡片居中、`max-width:720px`；
- 圆环存在且直径在 215–238px 之间；
- 圆环内时间是 39–44px 的大字；
- 「本次已用 00:47:26」一行在圆环下方；
- 三个按钮居中。

截图存 `_shots_v113/timer_fixed.png`，与 demo 屏 5 对照。

**commit**：`fix(计时): 修复 CSS 未闭合导致整段样式失效`

---

### 批次 I · 拆掉脱钩的定价开关（P1-1 + P2-6）

**目标**：定价方式只有一个真源 `pricing_mode`，不再有两个开关。

**现状**

- `app/routers/shop.py:62` `pricing_permission` 只写 `item.auto_pricing`；
- `app/services/pricing_checks.py:34` 只读 `item.pricing_mode`；
- 于是调旧接口：`enabled=false` → `pricing_mode` 仍是 `recurring`，**每天照样重估**；`enabled=true` → 仍是 `once`，**永远不进队列**；
- 前端已改调 `PATCH /pricing-mode`，`RewardShop.vue:34` 的 `permission()` 成了死代码。

**涉及文件**

- `app/routers/shop.py:23-26`（删 `AutomaticPricingIn`，它就定义在本文件，不在 `app/schemas/`）
- `app/routers/shop.py:62-69`（删路由）
- `frontend/src/components/RewardShop.vue:34`（删 `permission()`；它直接拼路径，`api.js` 里没有对应方法）
- `app/routers/reward_quotes.py:99`（新建时的 `auto_pricing` 取值）

**具体改法**

1. **删** `POST /shop/items/{id}/automatic-pricing` 整个函数，以及 `AutomaticPricingIn`。
   保留 `PATCH /shop/items/{id}/pricing-mode` 作为唯一入口（它已双写 `auto_pricing`，见 `shop.py:41`）。
   **不要**改成「旧接口内部转调新逻辑」——那样只是把两个入口变成一个入口的别名，下次还会有人调错。
2. 删前端 `permission()`（`RewardShop.vue:34`），删完 `grep -rn "automatic-pricing\|permission(" frontend/src/` 应为空；`app/routers/shop.py` 的 docstring 一并清理。注意模板里若还有调用它的按钮，一并删掉按钮，**不要留下点了没反应的入口**。
3. `reward_quotes.py:99`：`auto_pricing=row.payload.get('auto_check',False)` → `auto_pricing=False`。
   原因：同一行已经写死 `pricing_mode='once'`，而前端 `price()` 固定传 `auto_check:true`，于是新建出来的商品是「`pricing_mode=once` 但 `auto_pricing=True`」的自相矛盾状态。改完后两个字段一致。
   **`QuoteIn.auto_check` 保留不动**——`reward_quotes.py:131` 把它作为 `automatic_permission` 传给模型，影响 `worth_note` 的措辞，有真实用途。

**验收**

- 新建一件心愿 → 库里该商品 `pricing_mode='once'` 且 `auto_pricing=0`；
- `PATCH /pricing-mode` 切到 `recurring` → 两个字段同时为真；
- `grep -rn "automatic-pricing\|AutomaticPricingIn" app/ frontend/src/` 为空；
- `python -m unittest discover -s tests` 不新增失败。

**commit**：`refactor(商店): 定价方式只保留 pricing_mode 一个开关`

---

### 批次 J · 让数字和理由对得上（P1-3 + P1-2）

**目标**：同一张卡上不出现两个互相打脸的数字；理由里不再残留已废弃的价格。

**J-1 分析页每条显示的币数（`FactAnalysis.vue:47`）**

现状：标题行打印 `item.coins`（模型建议值），而下面一行打印 `preview` 里的 `breakdown.amount`。`eligible=False` 时 amount 是 0，于是同一张卡出现：

```
阅读 30 分钟
12 币 · 可信度 62%          ← item.coins
本项新增 0 币               ← preview.amount
```

这正是商店那边被判定为「自相矛盾」的同一类问题。

改法：**有 preview 就以 preview 为准**。

```js
function shownCoins(group, item) {
  const row = group.preview?.items?.find(i => i.fragment_id === item.fragment_id);
  return row ? (row.breakdown?.amount ?? 0) : item.coins;
}
```

模板里 `{{ item.coins }} 币` → `{{ shownCoins(group,item) }} 币`。
没有 preview 时仍是模型的建议值（此时用户还没生成入账预览，看到建议值是对的）。

**现成参考写法**：`EventFactAnalysis.vue:73` 的 `previewItem(item)?.breakdown.amount` 已经是这个口径——它从来只显示 preview 值，所以**事件分析页没有这个问题，不要动它**。改 `FactAnalysis.vue` 时照它的取值方式抄即可。

**J-2 退回并冻结不写脏理由（`shop.py:56`）**

现状：

```python
item.pricing_reason=(item.pricing_reason or '')+f'（退回 {previous} 币并冻结自动定价）'
```

F11 整轮的目的就是「理由里写的数字 = 界面显示的价格」。退回一次，理由里留着模型原本写的 48，界面是 30；退回两次追加两遍。

改法：

1. **删掉这一行**，`pricing_reason` 保持模型原句，一个字不改；
2. 审计写到 `PricingQuote`：

   ```python
   import hashlib
   from uuid import uuid4
   db.add(PricingQuote(
       user_id=user.id, item_id=item.id, state='rollback',
       request_key=str(uuid4()), fingerprint=hashlib.sha256(f'rollback:{item.id}:{previous}'.encode()).hexdigest(),
       payload={'previous_price': item.coin_price, 'target_price': previous},
       context={'mode_before': item.pricing_mode},
       result={'coin_price': previous, 'pricing_mode': 'once'}))
   ```

   `PricingQuote` 有 `UniqueConstraint('user_id','request_key')`，用 `uuid4()` 保证可重复点；`fingerprint` 是必填 `String(64)`，用 sha256 补齐。
   **字段以 `app/models/full_system.py:156-169` 的实际定义为准，不要为写审计去放宽任何约束。**

3. **界面上什么也不加**。退回记录只在库里留痕，商品卡的「依据」仍只显示模型原句——用户没要求看到退回历史，别自己加一行。

**验收**

- 确认一批币 → 记下 `item.coins` 与 `preview.total`；改一项的处置方式后重新预览，标题行的币数**随之变化，不再恒等于模型建议值**；
- 同一行动已入账（`booked=true`）时，标题行与「本项新增」**都是 0**；
- 连续点两次「退回并冻结」：`pricing_reason` **一字未变**，`pricing_quotes` 多两条 `state='rollback'`；
- 界面上的理由文本里搜不到「退回」。

**commit**：`fix(入账): 分析页币数以入账预览为准 · 退回不再污染定价理由`

---

### 批次 K · 收尾小项（P2-1 ~ P2-5）

| 编号 | 改法 | 验收 |
|---|---|---|
| **P2-1** | `set_pricing_mode`（`shop.py:34`）与 `rollback_price`（`shop.py:47`）补 `receipts.replay` / `receipts.record`；照 `disable_item`（`shop.py:170-176`）的写法——同样是 `MutationIn` + 改一个字段 + 返回 item，最贴切。（**不要**照 `pricing_permission`，批次 I 会把它删掉） | 同一 `request_key` 连点两次，第二次返回首次结果而非 409 |
| **P2-2** | 两个接口返回前查一次 `redeemed_count` 传给 `_item_out()`（现成写法见 `list_items`） | 已兑过的券切组后，不会出现在「只用这一次」列表里 |
| **P2-3** | `fact_analysis.py:201` 文案 `行动判档规则已变化，请重新分析。` → `定价规则已变化，请重新分析。` | 库里 `grep "判档"` 为空 |
| **P2-4** | `trial.py:26` 的 `action_used` 改为**当日全口径入账**：从 `coin_ledger` 汇总当天 `delta > 0` 且 `source != 'redemption'` 的记录。理由：上限已取消（F4），这个数只用于显示「今日已得」，不该只算手账那一块 | 同一天记一条手账 + 领一次首记，界面「今日已得」= 两者之和 |
| **P2-5** | `SiteFooter.vue:9` 的自绘图标**不动**，等用户提供备案系统给的官方图片后再替换；本轮只在模板旁留一行 `<!-- TODO(备案): 换官方图标，等素材 -->` | 页脚仍能正常显示，不报错 |

**P2-4 注意**：改的是**展示口径**，不是入账逻辑。`coin_service.grant()` 是唯一写入口这条不能碰；这里只加一个只读查询。查询要在 `coin_service` 里新增 `day_total()`，不要在图路由里直接拼 SQL。

**本批分两个 commit**（一个逻辑单元一个）：

- `fix(商店): 定价接口补幂等与兑换数`（P2-1、P2-2）
- `fix(手账): 今日已得改为当日全口径`（P2-3、P2-4、P2-5 一起带，都是文案/口径/注释级改动）

---

### 批次 L · 让 3 个既有测试跟上实现（P3-1）

**定性**：这 3 项在 `3fa0de7` 基线上**同样失败**，不是 v1.13 引入的。但既然根因已查清，修掉。

| 用例 | 根因 | 改法 |
|---|---|---|
| `test_all_business_routes_require_auth_and_confirmation_fault_stages_rollback` | 补丁打在 `coin_service.reward_event_confirm` 上，但 `judgments.py:181` 现在遇到 `event.economy_version` 就提前 409，**压根走不到奖励那段** | 断言改成「命中 409 且未写币」，或把注入点移到 `economy.award` |
| `test_redemption_replay_receipt_ownership_conflict_and_fault_rollback` | `/api/shop/items` 返回空列表，`items[0]` 越界（预置商品没种上） | 用例开头显式调一次预置（`shop_service.ensure_presets`），再取 id |
| `test_frontend_real_http_redemption_chain` | 同上，环境预置缺失 | 同上 |

**原则：改测试，不改实现。** 动代码前先确认「实现是不是本来就应该这样」——上面三条都是测试没跟上实现演进，实现是对的。
**改的过程中如果发现实现真错了，停下来单开一条，不要顺手改实现再改测试把两边对齐。**

**验收**：`./.venv/Scripts/python.exe -m unittest discover -s tests` → 无 failure / 无 error（用例总数可能因改动增减，**以 0 失败为准**）。

**commit**：`test: 对齐判定确认与商店预置的既有用例`

---

## 三、整体验收

1. **后端**：`cd my-life-rpg && ./.venv/Scripts/python.exe -m unittest discover -s tests` —— 全绿（批次 L 之后应无 failure / error）。
2. **前端**：`cd frontend && npm run build` 通过；**另外**定睛看三个页面：计时页（H）、分析页某条低置信度碎片（J-1）、商店退回一次后的商品卡（J-2）。
3. **迁移**：在 `b025` 库副本上 `alembic upgrade head` 成功，`alembic heads` 单一 head，`\d shop_items` / `\d experience_preferences` 列齐全。
4. **数据零改动**：本轮全程不碰真实库的既有行；`coins` / `events` / `attribute_history` / `coin_ledger` 四个数在改前改后一致（照 v1.13 的做法记录）。
5. **发布闸门**：`ops/` 里不再有 `b025_daily_use` 的断言；带迁移的发布流程**尚未执行**，等用户点头。

---

## 四、本轮明确不做

| 事 | 原因 |
|---|---|
| 真跑一次带迁移的云端发布 | 涉及停写窗口与回滚策略，需用户拍板（批次 G 第 5 条） |
| 换公安备案官方图标 | 需要用备案系统提供的图片，自绘的不合规也无法凭空生成 |
| 删 `ShopItem.auto_pricing` 列 | 老数据兼容，双写保平安，下个版本再清理 |
| `first_record` 的 +3 | 奖励的是「记录这个动作」，与「不要定死金额」不冲突（v1.13 已定） |
| 服务端每夜定时定价 | 仍是打开商店页触发，另开工 |
| 给流水页加归因 / 日记展开逐条 | 用户两次明确否决 |

---

## 五、文档回写（写完代码必做）

1. `docs/DEV_PLAN_v1.13.md` 末尾「实施结果」补一行：`P0-1` 迁移缺口由 `DEV_PLAN_v1.13.1.md` 补齐，附 commit。
2. `docs/learning/CODE_GUIDE.md` 第 11 章「Bug Ledger」按五栏建档**三条**：
   - **B-81**：`pricing_mode` 只加模型不写迁移 → 云端 `UndefinedColumn`、商店页 500（现象 → 定位过程含 `alembic heads` 与 `\d shop_items` 证据 → 根因是云模式不走 `migrate_schema` → 修复 → 防复发：**加列必查 `alembic/versions/`**）
   - **B-82**：CSS 少一个 `}` 导致整段样式被吞 → 计时页「改了跟没改一样」（防复发：**改 CSS 必起服务截图**）
   - **B-83**：双开关脱钩 → 关掉自动定价仍每天重估（防复发：**同一语义只能有一个真源，旧字段只写不读要显式标注**）
3. `docs/learning/BUSINESS_ROADMAP.md` 阶段 4 补一段叙事：为什么「±20% 截断」和「限幅调价」这类看起来稳妥的做法，反而制造了「理由与数字不一致」——**一致性比保守更重要**。
4. `docs/DECISIONS.md` 在 F11～F13 段后补「v1.13.1 修复项」小节，把本文件〇节表格抄一份，勾选后附 commit。

---

## 六、实施结果

| 批次 | commit | 实际落地 | 与本文档的偏离 |
|---|---|---|---|
| G | `ae32c85` | `b026_pricing_mode` / `b027_suppressed_lines` 两个 revision；`app/database.py` 回填改 `IS TRUE`；`ops/expected_head.py` 从 `alembic/versions` 现算 head；`update-public.sh` 断言动态化 + 回滚三段语义（库未变 / 库已新 schema / 未知）；`capture()` 新增 `require_head` 开关 | ① 新增 `ops/expected_head.py`（文档只说「现算」，没规定载体；宿主机 `python3` 装不了 alembic，用正则解析 revision 链最稳）；② 彩排改 `capture(require_head=False)`——彩排还原的是**迁移前**的备份，若强制等于新 head，带迁移的发布会在彩排阶段被自己拒掉；③ `update-public.sh:67` 比对的是**发布前**的库 head（`database_head`），不是新 head |
| H | `8002e5b` | 删掉重复且未闭合的 `.timer-ring` 半段，保留完整一份 | 无。截图实测：卡 720px 居中、圆环 238px、字号 44px、「本次已用」在环下、按钮同心 |
| I | `700ceb3` | 删 `automatic-pricing` 路由与 `AutomaticPricingIn`、删前端 `permission()`、新建奖励 `auto_pricing=False` | **额外修一处同类脱钩**：`disable_item` 原来只写 `auto_pricing=False`，`pricing_mode` 仍是 `recurring`，恢复后当晚又进重估队列；改为两个字段一起写（界面文案本来就承诺「停止自动价格检查」） |
| J | `59e6c5b` | `shownCoins()` 以 `preview.breakdown.amount` 为准；退回不再改 `pricing_reason`，改写 `pricing_quotes(state='rollback')` 审计 | 无。截图实测「0 币 · 可信度 62%」与「本项新增 0 币」一致 |
| K | `2042b87` / `184cf04` | 定价接口补 receipts 与 `redeemed_count`；409 文案去「判档」；`coin_service.day_total()`；备案图标留 TODO | ① `day_total()` 除 `redemption` 外**再排除 `onboarding_bonus`**——启动资金不是「今天赚的」，第一天显示 83 币会更误导；② 加 receipts 后 `PATCH pricing-mode` / `POST price-rollback` 在云模式需要 `request_key`，前端 `useWorkflowWrite` 本来就自动带，测试调用点补了 `request_key` |
| L | `a2e48d3` | 三个既有用例跟上实现：旧确认链路显式还原 `economy_version=None` + 有效来源快照；商店用例自己 `seed_preset_items()` 并直接写价 | ① 没有按文档「断言命中 409」了事——那样会丢掉故障回滚的覆盖，改为把用例恢复成**真的能走到奖励路径**的旧事件；② `tests/frontend_release.mjs` 另补两处环境缺口：漏加载 `requestStatus.js`、`ChallengeView.redeem` 现在要 `confirmed=true` 才提交 |

**整体验收**：`python -m unittest discover -s tests` → **298 项，`OK (skipped=11)`，0 failure / 0 error**；
`vite build` 通过；`alembic heads` 单一 head `b027_suppressed_lines`，离线渲染的升级 SQL 为
`ALTER TABLE shop_items ADD COLUMN pricing_mode ... DEFAULT 'once' NOT NULL` + `UPDATE ... WHERE auto_pricing IS TRUE` + `ALTER TABLE experience_preferences ADD COLUMN suppressed_lines JSON`；
本地 SQLite 副本 `migrate_schema` 正常（`auto_pricing=1 → recurring`，其余 `once`）；真实库零改动；
`grep -rn "b025_daily_use" ops/` 为空。**带迁移的发布尚未执行，等用户点头。**

---

## 七、补漏（第二轮审查，2026-11-17 晚）

六批提交后我又把 7 个代码 commit 读了一遍，发现三处需要收尾。本节记录**已落地的两处**和**经核实不必改的一处**。

### 7.1 P2-4 只改了一半：同一个词在两个页面显示两个数

`/api/trial` 的 `action_used` 已经换成 `day_total()`（全口径），但**分析页从来不用这个接口**：

- `FactAnalysis.vue:57`、`EventFactAnalysis.vue:78` 读的是 `group.preview.used`
- `preview.used` 来自 `app/services/fact_analysis.py:200` 的 `trial_rules.cap_used()`——只 `sum(ActionAward)`
- `:138` 喂给模型的 `today_coins` 是同一个旧口径

于是设置页 28、分析页 25，差额正是当日首记的 3 币。**这批要消灭的是"同一含义两个数"，结果自己又造了一个。**

**改法**（`46a0085`）：两处都换成 `coin_service.day_total(db,user,day)`；`cap_used()` 全仓无引用，删除。

**回归覆盖**（`69974f4`）：`tests/test_v1131_today.py` 补一条——同日发 25 币 + 首记 3 币后，
`preview.used` 与 `/api/trial` 的 `action_used` 必须都是 28。此前全仓**没有任何用例断言过 `preview.used`**，
这正是它漏到界面的原因。

**副作用（预期，需事先知道）**：`confirm()` 有 `bundle.preview != preview(...)` 就 409 的一致性校验。改口径后，
**改之前生成、还没确认的草稿**会在下次预览时被要求重新生成一次。与 F4 升 `rule_version` 时同样的效果，不是回归。

### 7.2 测试写死迁移 head

`tests/test_v1131_ops.py:24` 原断言 `head(ROOT) == 'b027_suppressed_lines'`。加一个 `b028`，这条就会红，
而它要保护的正是"不要每次都手改 head"。**改法**（`a46d25d`）：`assertIn(head(ROOT), known_revisions(ROOT))`
——`head()` 本身在多头时会抛 `MULTIPLE_HEADS`，所以"唯一"仍被覆盖。

### 7.3 「停用降级」保留，且它不是新行为

批次 I 里 `disable_item` 额外写了 `pricing_mode='once'`，我原先标注为"改了行为"，核实后需要更正：

| 版本 | 停用时写什么 | 重新启用后 |
|---|---|---|
| v1.12 `3fa0de7` | `enabled=False` + `auto_pricing=False` | `auto_pricing` 仍为 False，不会自己恢复 |
| v1.13（修前） | `enabled=False` + `auto_pricing=False` | `pricing_mode` 仍是 `recurring` → 当晚重新进队列（**这才是 bug**） |
| v1.13.1（`700ceb3`） | `enabled=False` + 两个字段一起写 | 停在 `once`，与 v1.12 表现一致 |

结论：`pricing_mode='once'` 只是把 v1.12 的既有语义搬到新列，**不制造新的"降级"**。想恢复跟随行情，
在商品里点一次「改成常用兑换券」即可，这个入口本来就在。**不改。**

### 7.4 顺带核实、确认不需要动的

- **`EventFactAnalysis.vue` 没有 P1-3 那个问题**：`:73` 早就只显示 `previewItem(item)?.breakdown.amount`，
  批次 J 只动 `FactAnalysis.vue` 是对的，别"顺手统一"。
- **前端定价接口不需要手动传 `request_key`**：`useWorkflowWrite.send()` 自动注入 `crypto.randomUUID()`，
  且刷新后保留同一个 key（只用于重试），所以补 receipts 不会在云端变成 422。
- **`b026` 的写法正确**：先 `add_column(server_default='once')`，再在同一次 `upgrade` 内用 `IS TRUE` 回填。
- **新用户商店是空的**（`seed_preset_items` 在 `9a05d53` 就停止在 `list_items` 里调用，v1.12 也没有）。
  这是既有产品状态，不属于本轮范围；要不要恢复预置或给空态入口，另议。

**本节验证**：`python -m unittest discover -s tests` → **299 项 `OK (skipped=11)`**（六批收尾时 298，本节新增回归用例 1 条）；
测试从这一版起不再因加迁移而红。
