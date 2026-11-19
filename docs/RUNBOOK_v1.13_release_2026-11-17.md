# v1.13 上线 Runbook（首次带 schema 迁移）

> **基线**：本地 `main` 领先 `origin/main` 约 27 个 commit（v1.13 + v1.13.1 + 本文档）；**以 `git rev-list --count origin/main..HEAD` 现场取数为准**
> **线上现状**：镜像 `3fa0de7`（v1.12），库 head `b025_daily_use`
> **本次要迁的**：`b026_pricing_mode`（`shop_items.pricing_mode`）、`b027_suppressed_lines`（`experience_preferences.suppressed_lines`）
> **决策**：走"路线 1"——迁移作为独立前置步骤，不改发布脚本
> **执行人**：全部命令由你在服务器执行；本文档只出步骤与检查点

---

## 0. 为什么不能直接跑 `update-public.sh`

不是保守，是脚本里两道断言互斥，逐行核过：

| 位置 | 断言 | 含义 |
|---|---|---|
| `update-public.sh:132` | `new_compose run ... init_db()` | 新镜像启动检查要求 `alembic_version` **等于本包 head**，否则 `raise RuntimeError("数据库版本未就绪，请先单独执行迁移。")` |
| `update-public.sh:96` | 彩排结果的 `head == database_head` | 彩排备份的版本必须等于**脚本启动时**（`:45`）读到的库版本 |

于是：

- **不先迁移** → preflight 的 `init_db()` 直接失败，脚本停（安全，但白跑）
- **先迁移、却拿迁移前的备份彩排** → 第 96 行断言失败，脚本停（安全，也白跑）

**唯一不需要改代码的顺序**：先迁移 → 用**迁移后**的备份彩排 → 再跑 `update-public.sh`。这时脚本读到的 `database_head` 和彩排备份的 head 都是 `b027`，两道都过。

### 总顺序

| 步 | 动作 | 是否停写 | 失败会怎样 |
|---|---|---|---|
| A | 本地 push + CI 出包 | 否 | 无影响 |
| B | 上传、校验、装载镜像 | 否 | 无影响 |
| C | 迁移前备份 | 否 | 无影响 |
| D | `alembic upgrade head` | **不需要停写** | 事务回滚，库仍 `b025` |
| E | 迁移后备份 | 否 | 无影响 |
| F | 彩排（隔离库副本） | 否 | 不切换，可延后 |
| G | `update-public.sh` | **是，几分钟** | 脚本自带回滚 |
| H | 上线后验证 | — | 按第 9 节处置 |

**D 为什么不用停写**：本次只做 `ADD COLUMN`（`b026` 带 `server_default`，PG 11+ 纯改系统目录、不重写表；`b027` 是可空 JSON 列）。当前运行的 v1.12 代码只 SELECT 自己映射的列，多出来的列它看不见，所以旧代码可以继续服务。`shop_items` 是小数表（D1 会打印实际行数），取 ACCESS EXCLUSIVE 锁是毫秒级。

---

## 1. 阶段 A：本地推送 + 出包

### A1 推送（注意代理）

```bash
cd "C:/Users/19687/Desktop/游戏人生/work_place/my-life-rpg"
git rev-list --count origin/main..HEAD            # 记下这个数（本次约 27）
git -c http.proxy= -c https.proxy= push origin main
git status -sb | head -1                         # 应为 ## main...origin/main 且无 ahead
```

> 本机走 `127.0.0.1` 代理会推失败，必须 `-c http.proxy= -c https.proxy=` 直连。`gh` 同理，需要先清空代理环境变量。

### A2 出包

```bash
gh workflow run "Build deployment bundle" --repo X-xu-X/my-life-rpg --ref main
gh run list --repo X-xu-X/my-life-rpg --workflow "Build deployment bundle" --limit 1
gh run watch <RUN_ID> --repo X-xu-X/my-life-rpg
```

**检查点**：run 的 `conclusion` 为 `success`，`head_sha` 等于第 A1 步 push 后的 `git rev-parse HEAD`（记下这个 **40 位 SHA**，后面 G 阶段要用）。

### A3 下载（**必须在 24 小时内**）

> **制品只保留 1 天。** `.github/workflows/build-deployment-bundle.yml:134` 写死了 `retention-days: 1`。
> 昨天晚上那次构建（run `44088146731`）页面报 `Failed to generate URL to download artifact`，
> 不是网络问题，是**制品在 24 小时后被删了**——查 `gh api .../runs/<id>/artifacts` 返回 `total_count: 0`，
> 而那次运行的 `Upload the private deployment bundle` 步骤本身是 success。
>
> 为什么是 1 天：单包 310MB，私有仓 Actions 存储免费额度 500MB。留多天会两个包并存直接超配额，
> 后续上传就会失败。所以**别把 retention 调大**，改法只有一个：构建完当天就下载。

```bash
cd "C:/Users/19687/Desktop/游戏人生/work_place"
mkdir -p _deploy-<short>
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  gh run download <RUN_ID> --repo X-xu-X/my-life-rpg \
  --name "lifexp-linux-amd64-<40 位 SHA>" --dir "_deploy-<short>"
```

下载下来的是一个**目录**（不是 zip 里的 zip），里面应当有：

```
BUILD_RECEIPT.json
SHA256SUMS
images-<release>.tar.gz
images-<release>.manifest.jsonl
images-<release>.tar.sha256
rr-<...>.manifest.json
<release>.zip
IMAGE_STORE_COMPAT.json  PRODUCTION_CONTAINERD_VERIFY.json
```

**检查点**：

```bash
cd _deploy-<short> && sha256sum -c SHA256SUMS
```

不通过就重下，别带着错包上传。

> **`gh run download` 可能长时间没有任何输出**（它不打印进度，且会先缓存整包再解压）。如果超过几分钟目录还是空的，
> 别再等，改用直链自己取：
> ```bash
> TOKEN=$(env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY gh auth token)
> curl -L -H "Authorization: Bearer $TOKEN" \
>   "https://api.github.com/repos/X-xu-X/my-life-rpg/actions/artifacts/<ARTIFACT_ID>/zip" \
>   -o artifact.zip
> ```
> 实测单连接只有 ~40KB/s（走代理还更慢，~26KB/s），310MB 要两小时。**按字节分 8 段并发**可以到 ~320KB/s，
> 约 17 分钟：每段 `curl -L -r <start>-<end>`，下完按顺序 `cat part.00 part.01 ... > artifact.zip`。
> 段内失败就重取一次 `Location`（签名 URL 有时效），再续。合并后 `unzip -t artifact.zip` 验证完整性。

---

## 2. 阶段 B：上传与装载

```bash
# 本地：把整个目录传上去，外加 receive-local.sh
scp -r _deploy-<short>/* admin@lifexp.cn:~/upload-<short>/
scp receive-local.sh admin@lifexp.cn:~/
```

> `receive-local.sh` 不在仓库里，是上次发布时留在本地的（`_deploy-a53f14e2/receive-local.sh`）。
> 它和 `ops/receive-update.sh` 的校验链完全一致，只把"从 GitHub 下载"换成"用本地上传的目录"，末尾打印 `IMAGES_READY`。

```bash
# 服务器
bash ~/receive-local.sh ~/upload-<short> <40 位 SHA>
```

它做的事依次是：把上传的文件移进 `~/lifexp-<short>.XXXXXX/` → `sha256sum -c SHA256SUMS` → 校验 `BUILD_RECEIPT.json` 的 `git_head`/`release_id` → 解 `<release>.zip` 到 `source/` → `verify_package.py` → 解压镜像 tar 并 `image_identity verify-archive` → `docker load` → `image_identity verify`。

**记下它最后打印的两个值，后面每一步都要用**：

```
IMAGES_READY
SOURCE_DIR=/home/admin/lifexp-<short>.XXXXXX/source
RELEASE_ID=rr-<...>
```

**检查点**：

```bash
sudo -n docker image inspect "game-of-life-api:<RELEASE_ID>" --format '{{.Id}}'      # 有输出
sudo -n python3 -B "<SOURCE_DIR>/ops/expected_head.py" "<SOURCE_DIR>"                # 必须打印 b027_suppressed_lines
sudo -n docker inspect game-of-life-api-1 --format '{{.Config.Image}}'               # 仍是旧 release
```

`expected_head.py` 打印的不是 `b027_suppressed_lines`，**停止**——说明包不对，别往下走。

---

## 3. 阶段 C：迁移前备份（保命用）

```bash
SHORT=<short>; TS=$(date -u +%Y%m%dT%H%M%SZ)
sudo -n docker exec game-of-life-db-1 pg_dump -U gol_admin -d game_of_life --format=custom \
  > ~/gol-premigrate-$SHORT-$TS.dump
test -s ~/gol-premigrate-$SHORT-$TS.dump && echo BACKUP_OK
sudo -n docker exec -i game-of-life-db-1 pg_restore --list < ~/gol-premigrate-$SHORT-$TS.dump | head -5
sha256sum ~/gol-premigrate-$SHORT-$TS.dump
```

**检查点**：`BACKUP_OK` 打出，`pg_restore --list` 能正常列出内容（不是报错），sha256 记下来。

---

## 4. 阶段 D：执行迁移

### D1 先看一眼现状

```bash
sudo -n docker exec game-of-life-db-1 psql -X -U gol_admin -d game_of_life -At \
  -c "SELECT version_num FROM alembic_version"                       # b025_daily_use
sudo -n docker exec game-of-life-db-1 psql -X -U gol_admin -d game_of_life -At \
  -c "SELECT count(*) FROM shop_items"                               # 记下这个数，D3 要用
```

### D2 迁移

用**新包的 compose 文件** + **当前的 env 文件**，只跑 `migrate` 这个一次性服务（compose 里 `profiles: [ops]`，`command` 就是 `python -m alembic upgrade head`；容器入口 `entrypoint.py` 会从 `/run/secrets/app_password` 拼出 `DB_URL`，不把 DSN 写进命令行）：

```bash
sudo -n bash -c 'ls -1 /etc/game-of-life/*.env'
OLD_ENV=/etc/game-of-life/public-<oldshort>.env
```

> **这里不会只有一个 env 文件。** `update-public.sh:34` 写的是 `new_env=/etc/game-of-life/public-$short.env`（`short=${SHA:0:8}`），
> 发一版留一个，累积下来有六七个（2026-11-19 实测 7 个）。要用的是**当前在跑的那个 release** 对应的：
> 先 `sudo -n docker inspect game-of-life-api-1 --format '{{.Config.Image}}'` 拿到 `game-of-life-api:rr-<日期>-<short>-<hash>`，
> 中间那段 `<short>` 就是文件名里的字符。
>
> 另外 `sudo -n ls -l /etc/game-of-life/*.env` 会报 `No such file or directory`——`*` 是**当前用户 shell 先展开**的，
> 而该目录是 700；要写成 `sudo -n bash -c 'ls -l /etc/game-of-life/*.env'` 让 root 去展开。
>
> 不手抄路径的写法：`sudo -n bash -c '. /etc/game-of-life/public-<short>.env; echo "$SECRETS_DIR"; ls -l "$SECRETS_DIR"'`，
> 应看到 `admin-password`、`app-password`、`credential-keys.json` 三个文件。

```bash

sudo -n env RELEASE_ID="<RELEASE_ID>" \
  docker compose --project-name game-of-life --env-file "$OLD_ENV" \
  -f "<SOURCE_DIR>/deploy/compose.prod.yml" \
  run --rm --no-deps --pull never --interactive=false -T \
  -e PGOPTIONS="-c lock_timeout=5000 -c statement_timeout=60000" \
  migrate
```

**预期输出**（结尾两行）：

```
Running upgrade  b025_daily_use -> b026_pricing_mode
Running upgrade  b026_pricing_mode -> b027_suppressed_lines
```

如果 compose 报 `service "migrate" is not enabled`（profiles 挡了），在 `run` 前加全局参数 `--profile ops`：`docker compose --profile ops run ...`，其余不变。

### D2-补：b027 报 `DuplicateColumn` 时怎么办

>b 实测发生过一次（见第 12 节）。`b027` 假设"云端从 b025 建表起就漏了 `suppressed_lines`"，
> 但这列可能早已存在（模型里有，某次 `create_all` 顺手建上了），只是 `alembic_version` 没跟着推进。
>
> 因为 `alembic/env.py` 没有 `transaction_per_migration`，`upgrade head` 是**一个事务**：
> b026 加列 + 回填会随 b027 的失败**一起回滚**，库回到 b025，不留半成品。
>
> 处置分两步，不重出包：
>
> ```bash
> # 1) 只跑到 b026（用 run 覆盖 command）
> sudo -n env RELEASE_ID="<RELEASE_ID>" docker compose --project-name game-of-life \
>   --env-file "<OLD_ENV>" -f "<SOURCE_DIR>/deploy/compose.prod.yml" \
>   run --rm --no-deps --pull never --interactive=false -T \
>   -e PGOPTIONS="-c lock_timeout=5000 -c statement_timeout=60000" \
>   migrate python -m alembic upgrade b026_pricing_mode
> #    校验：head=b026_pricing_mode，且 pricing_mode 分组行数合计 = D1 的 count(*)
>
> # 2) 先确认目标结构现成，再登记
> #    psql 查 information_schema：suppressed_lines 必须是 json/json/YES
> sudo -n env RELEASE_ID="<RELEASE_ID>" docker compose --project-name game-of-life \
>   --env-file "<OLD_ENV>" -f "<SOURCE_DIR>/deploy/compose.prod.yml" \
>   run --rm --no-deps --pull never --interactive=false -T \
>   migrate python -m alembic stamp b027_suppressed_lines
> ```
>
> **`stamp` 只在"类型、可空性逐项对得上"时才等价于真跑一遍 `add_column`**；类型是 `jsonb` 或 `text` 就不能这么办，
> 要先单独评估。顺序也不能反：`stamp` 不执行 DDL。`b026`/`b027` 的 `downgrade()` 都直接 `raise`，回退只能从备份隔离恢复。

`lock_timeout` 是为了万一有长事务占着 `shop_items` 时**干净地失败**而不是把后面所有请求堵住；5 秒退出来再重试即可。

### D3 校验（必须逐条对）

```bash
sudo -n docker exec game-of-life-db-1 psql -X -U gol_admin -d game_of_life -At \
  -c "SELECT version_num FROM alembic_version"

sudo -n docker exec game-of-life-db-1 psql -X -U gol_admin -d game_of_life -At -F'|' -c \
"SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns
 WHERE (table_name='shop_items' AND column_name='pricing_mode')
    OR (table_name='experience_preferences' AND column_name='suppressed_lines')"

sudo -n docker exec game-of-life-db-1 psql -X -U gol_admin -d game_of_life -At -c \
  "SELECT pricing_mode,count(*) FROM shop_items GROUP BY 1 ORDER BY 1"

curl -fsS https://lifexp.cn/service-status      # 旧代码仍在服务，应为 ready
```

**期望**：
- head = `b027_suppressed_lines`
- 两行：`shop_items|pricing_mode|character varying|NO|'once'::character varying`、`experience_preferences|suppressed_lines|json|YES|`
- `pricing_mode` 分组只有 `once` 或 `recurring`，各组行数**合计等于 D1 记下的 count(*)**（说明回填没丢行）
- `/service-status` 仍是 `ready` —— 旧代码对新列完全无感

**任一条不符 → 停手，不要进入 E**，按第 9 节处置。

---

## 5. 阶段 E：迁移后备份（彩排输入 + 回滚源）

必须重新备份：C 阶段那份是 `b025`，拿去彩排会被 `update-public.sh:96` 判失败。

```bash
SHORT=<short>; TS=$(date -u +%Y%m%dT%H%M%SZ)
sudo -n docker exec game-of-life-db-1 pg_dump -U gol_admin -d game_of_life --format=custom \
  > ~/gol-postmigrate-$SHORT-$TS.dump
test -s ~/gol-postmigrate-$SHORT-$TS.dump && echo BACKUP_OK
sudo -n docker exec -i game-of-life-db-1 pg_restore --list < ~/gol-postmigrate-$SHORT-$TS.dump > /dev/null && echo RESTORE_LIST_OK
sha256sum ~/gol-postmigrate-$SHORT-$TS.dump
```

> 备份文件必须留在 `/home/admin` 下且名字是 `gol-*.dump`——彩排脚本和第 96 行断言都按这个规则校验。

---

## 6. 阶段 F：彩排（隔离库副本，不碰生产）

```bash
free -m | head -2          # MemAvailable 需 ≥ 700MB，否则脚本直接拒跑
bash "<SOURCE_DIR>/ops/rehearse-public-update.sh" "<SOURCE_DIR>" ~/gol-postmigrate-<short>-<TS>.dump
```

（第二个参数填 E 阶段那个备份的完整文件名。）

**预期输出**：

```json
{"status": "ISOLATED_PG_REHEARSAL_PASS", "head": ["b027_suppressed_lines"], "restored_tables": <表数>, ...}
PRODUCTION_CONTAINERS_UNCHANGED
EVIDENCE_DIR=/home/admin/lifexp-rehearsal.XXXXXX
```

**记下 `EVIDENCE_DIR`，G 阶段第 4 个参数就是它里面的 `result.json`。**

**检查点**：
- `head` 是 `["b027_suppressed_lines"]`（不是 b025）
- `business_writes` 为 `NONE`
- `PRODUCTION_CONTAINERS_UNCHANGED` 打出

失败就停在这里。此时库已是 `b027`、旧代码照跑，站点正常，可以改日再发——**没有必须今天发完的压力**。

---

## 7. 阶段 G：正式切换

```bash
sudo -n bash -c 'ls -1 /etc/game-of-life/*.env'      # 取当前正在用的那一个
ACTIVE_ENV=/etc/game-of-life/public-<oldshort>.env   # 与 D2 的 $OLD_ENV 是同一个文件

bash "<SOURCE_DIR>/ops/update-public.sh" \
  "<SOURCE_DIR>" \
  "<40 位 SHA>" \
  "$ACTIVE_ENV" \
  "/home/admin/lifexp-rehearsal.XXXXXX/result.json"
```

脚本第一件事就是 `sudo -n realpath -e` 校验这个路径必须是 `/etc/game-of-life/*.env`，填错或写成软链会直接退出。

脚本内部会依次打出这些标记，逐个对：

| 标记 | 含义 |
|---|---|
| `PREFLIGHT_PASS: starting brief write pause...` | 新镜像 `init_db()` 通过（**这里验证了库 head 已就位**） |
| `FINAL_BACKUP=/home/admin/gol-before-....dump` | 停写后立即整库备份 |
| `{"status": "DATA_UNCHANGED", ...}` | 前后快照比对一致（表数、序列数、业务行数都没动） |
| （无输出，但容器已切换） | api/worker/caddy 起新镜像并通过 healthcheck |
| （无输出，`cmp` 成功） | 线上首页与镜像内 `index.html` 逐字节一致 |

**停写窗口**：从 `starting brief write pause` 到最后容器切换完成。期间你打不开页面是正常的，不要中途 Ctrl+C。

---

## 8. 阶段 H：上线后验证

```bash
curl -fsS https://lifexp.cn/service-status                                   # ready
sudo -n docker inspect game-of-life-api-1 --format '{{.Config.Image}}'       # 新 release
sudo -n docker exec game-of-life-db-1 psql -X -U gol_admin -d game_of_life -At \
  -c "SELECT version_num FROM alembic_version"                               # b027_suppressed_lines
sudo -n docker logs --since 10m game-of-life-api-1 2>&1 | grep -iE "error|UndefinedColumn|traceback" | head
```

浏览器上逐项看：

1. **商店页能打开**、商品正常列出（不再 500）
2. 商品卡有「常用兑换券 / 只用这一次」分组与涨跌标记
3. **计时页**是居中卡 + 圆环 + 大号剩余时间
4. 记一条手账 → 分析结果里金币是 AI 给的具体数并带一句理由；「今日已得」与设置页一致
5. 页脚公安备案号在

---

## 9. 失败处置

| 阶段 | 现象 | 处置 |
|---|---|---|
| D 迁移 | `lock_timeout` / 报错退出 | 事务自动回滚，库仍 `b025`，旧代码完全正常。查 `pg_stat_activity` 有无长事务，重试即可 |
| D 校验 | head 不是 `b027` | **不要进入 E**。以 C 阶段备份为准核实；多半是 `alembic_version` 被写坏，先别动，把输出发我 |
| F 彩排 | 非 `PASS` | 不切换。库已是 `b027` 但旧代码不读新列，站点照常。把 `EVIDENCE_DIR` 里的 `result.json` 发我 |
| G 切换 | `UPDATE_STOPPED stage=...` + `OLD_SERVICES_RECOVERED` | 库回到旧版本、旧镜像已恢复，等于没发。看 `EVIDENCE_DIR` 里的日志 |
| G 切换 | `SCHEMA_AHEAD_OF_CODE` | 代码回滚到旧镜像、**库仍是 `b027`**。这不是"回退了"，是"库领先代码"。直接再跑一次 G 即可（D/E/F 都不用重做） |
| 上线后 | 商店 500 / `UndefinedColumn` | 说明 D 没真正生效。查 head，若仍是 `b025` 则补跑 D，再跑 G |

### 严重回滚（不从 alembic 回退）

`b026` / `b027` 的 `downgrade()` 都是直接 `raise RuntimeError`——**设计如此，不要试图 `alembic downgrade`**。要退回旧结构只能从备份隔离恢复：

1. 停 api/worker
2. 用 `~/gol-postmigrate-*.dump` 或 `~/gol-premigrate-*.dump` 恢复到**新库**并核对行数
3. 确认无误后替换数据卷，起旧镜像
4. 打 `RESTORED_FROM_BACKUP head=<实际值>`，写清是从哪一份备份、恢复到什么时间点

---

## 10. 两个需要知道的副作用

1. **D 与 G 之间**（可能几十秒到几分钟）旧代码仍在服务。若这时有人新增心愿，`pricing_mode` 会落到列默认值 `once`，切到新版后显示为「只用这一次」。可接受，不用处理；但别在这个窗口里刻意去做定价操作。
2. **`b027` 补的是 `experience_preferences.suppressed_lines`**。这一列在本地 SQLite 上一直由 `migrate_schema` 补，云端从 `b025` 建表起就漏了。上线后第一次读该表如果报 `UndefinedColumn`，说明 D 没成功，按第 9 节查。

---

## 11. 本次不做的事

- 不改 `ops/*.sh`（迁移阶段没写进脚本，`update-public.sh` 头注释描述的"停写窗口内执行迁移"目前靠人工落实）
- 不改 `ops/` 里的 head 断言（已由 `expected_head.py` 现算，不再是硬编码常量）
- 不恢复商店预置商品（`seed_preset_items` 在 `9a05d53` 就停止在 `list_items` 里调用，属既有产品状态）
- 不做服务端每夜定时定价（仍靠打开商店页触发 `pricingSweep.js`）

---

## 12. 2026-11-19 首发现场实录（实际路径与本文件假设的偏差）

首发没按理想路径一次跑完，两处偏差都已解决，留给下次参照。

### 12.1 已完成的步骤与关键值

| 步 | 状态 | 关键值 |
|---|---|---|
| A 推送出包 | ✅ | 包对应 `dadd42ed`，制品 id `14438770552`（`retention-days:1`，当天取） |
| B 接收装载 | ✅ | `SOURCE_DIR=/home/admin/lifexp-dadd42ed.oFcjU5/source`、`RELEASE_ID=rr-20261010-dadd42ed-3c0de1066873` |
| C 迁移前备份 | — | 实际未单独做（D 失败自动回滚，旧代码全程未受影响） |
| D 迁移 | ✅（分两步） | b026 正常；b027 撞 `DuplicateColumn` → `upgrade b026_pricing_mode` 后 `stamp b027_suppressed_lines`，head 终态 `b027_suppressed_lines` |
| E 迁移后备份 | ✅ | `~/gol-postmigrate-dadd42ed-20261119T003636Z.dump`（578 KB，`sha256 ddbf3062…`，head=b027） |
| F 彩排 | ❌ 第 1 次 | `REHEARSAL_STOPPED stage=restore-health-proof`，镜像内 `ops/rehearse_public_update.py` 语法错误（B-85） |

D 阶段校验实测：`shop_items` 共 10 条，回填后 `once 5 / recurring 5`；`/service-status` 全程 `ready`。

### 12.2 偏差一：b027 的列早已存在

`b027` 的注释假设云端缺 `experience_preferences.suppressed_lines`，实测**该列已在**（`json`/`json`/`NULL` 可空，与 `sa.JSON()`、`nullable=True` 逐项一致）。处置见「D2-补」。

**教训**：迁移的注释不能当成事实来源，**迁移前先查 `information_schema`**，别默认"版本号落后 = 结构也落后"。

### 12.3 偏差二：重新出包（B-85）

彩排失败根因是文件本身不可解析，不是环境问题。服务器上打补丁**不可行**：

- `update-public.sh:78`/`:110` 会跑 `verify_package.py`，按 `RELEASE_MANIFEST.json` 逐个核哈希 → 改源文件必失败，除非改清单（等于伪造）
- 探针跑的是**镜像内**的 `ops/rehearse_public_update.py`，而镜像 ID 被 `image_identity.py` 绑死在 `IMAGE_STORE_COMPAT.json` 上

所以必须重新出包。修法：删掉多余的 `"""`（`d6d329d`）+ 流水线加编译门（`7bbcd55`）。

**重新出包后只需重走 B → F → G**，C/D/E 全部不用重做：

- 库已经是 `b027`，`update-public.sh:132` 的 preflight 要求"库 head == 本包 head"，新包 head 仍是 `b027` ✅
- `update-public.sh:96` 要求"彩排备份 head == 脚本启动时读到的库 head"，E 那份备份正是 `b027` ✅

**唯一要注意**：新包出来后 `RELEASE_ID` 会变（新 SHA），`SOURCE_DIR` 也会变，之前记的值全部作废；E 阶段那份备份**继续有效**，彩排直接用同一个 dump 文件。

### 12.4 收尾清理

彩排每次会留下一个 `lifexp-proof-<xxxx>-pg` 数据卷（容器和网络会自动删）。确认 PASS 后清掉即可：

```bash
sudo -n docker volume ls --filter label=lifexp.scope=isolated-rehearsal
sudo -n docker volume rm lifexp-proof-<xxxx>-pg
```

另外 `/home/admin/lifexp-rehearsal.<xxxx>` 证据目录会保留（刻意留档），里面是 `result.json` 和 PG 日志，几十 KB，可以攒着。
