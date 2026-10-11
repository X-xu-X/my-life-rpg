# 云端预发与运维说明

> 2026-10-10：执行顺序以 [本轮预检清单](../docs/PREFLIGHT_DEPLOY_CHECKLIST.md) 为准，状态见 [本轮交付](../docs/RELEASE_READINESS_DELIVERY_2026-10-10.md)。本机尚无 Docker；Linux 镜像、目标 Compose、30 分钟观测、真实通知及异机恢复仍须实测。提供固定源码候选包，Dockerfile 不是镜像产物。不要开放正式邀请。

> 运维复审已修正端口误报、临时容器备份身份和仅首页探测；当前源码候选版及本机真实restic/Caddy验证见 [复审交付](../docs/OPS_REVIEW_FIXES_2026-10-10.md)。以下目标机步骤仍待执行。

> 2026-10-11：新构建采用 schema v2 原始镜像配置身份协议，兼容 classic/containerd 的不同外层 ID。旧清单必须重建；新包操作以 [离线构建指南](../docs/GITHUB_OFFLINE_BUILD_GUIDE.md) 为准。Linux 跨存储实测结果须查看本次 Actions 的 IMAGE_STORE_COMPAT.json，不能把已准备脚本记为通过。

> PostgreSQL 缺省 User 续修：安全读取 inspect 可选 User，仅缺省/null 与空字符串按同一语义比较，不改变原始配置摘要；应用 UID/GID 和 PG 用户／摘要／平台检查保留。CI 新增本次真实四个生产镜像的 containerd 导入验证，结果见 PRODUCTION_CONTAINERD_VERIFY.json；必须使用含续修的新包，不替换原835ebc2候选脚本。详见 [续修交付](../docs/POSTGRES_DEFAULT_USER_FIX_DELIVERY_2026-10-11.md)。

本包供经过授权的预发部署使用。2026-10-09 只在本机合成库完成 PostgreSQL 18.6、迁移、备份恢复和浏览器检查；当前电脑没有 Docker，镜像、Compose、Caddy、systemd、远端 restic 和真机网络尚未执行。不得据此开放正式邀请。完整状态见 [开发交付记录](../docs/NEXT_ITERATION_DELIVERY.md)。

## 运行与秘密文件

- 生产采用单 API、单 worker、PostgreSQL、Caddy；数据库不映射宿主机端口。`start.bat`/`start.sh` 仅供本地兼容模式，不能充当云端入口。
- API/worker 使用 UID 10001，非超级用户数据库角色 `gol_app`。`gol_admin` 仅用于初始化和隔离恢复。维护人员不得将生产服务切回 `RUN_MODE=local`。
- `deploy/.env.production.example` 只有占位符；实际配置放仓库外，例如 `/etc/game-of-life/production.env`，设置真实域名、邮箱、发布标识和三个目录。
- `SECRETS_DIR` 包含不同的随机长口令 `admin-password`、`app-password`，以及 `credential-keys.json`。数据库口令至少 24 字符，不能在命令行参数或日志中输出。
- 密钥可用开发环境 `python ops/manage.py generate-key --output <新的受限文件>` 创建；已有文件不会覆盖。它必须有独立离线副本，不与远端数据库备份共存于同一账户。
- 宿主机秘密目录限制为管理员可遍历。Compose 文件秘密挂载的 UID/GID 不负责修复宿主机权限：应显式授权 UID 10001 读取应用口令和加密密钥，并授权数据库镜像中的 postgres 用户读取数据库口令。先通过 `docker run --rm --entrypoint id postgres:18.6-bookworm -u postgres` 确定 UID，再配置 ACL；禁止把整个秘密目录设为公开可读。
- 只读根文件系统、资源限额和日志轮转已配置。需要在目标机器实测峰值内存和磁盘；前端镜像宜在构建机完成，避免小服务器构建时内存不足。

PostgreSQL 18 的数据卷挂在 `/var/lib/postgresql`，固定卷名为 `game_of_life_pg18`，不是旧版本常见的挂载位置。参见 [官方镜像说明](https://hub.docker.com/_/postgres)。Caddy 的公网证书须在域名解析、80/443 可达后实测，参见 [Automatic HTTPS](https://caddyserver.com/docs/automatic-https)。

## 首次预发

以下为目标 Linux 主机上的待执行命令，当前没有执行。先安装 Docker Compose，准备上述受限文件和下节 ops 配置，然后从固定发布目录运行：

```sh
export PRODUCTION_ENV_FILE=/etc/game-of-life/production.env
export RELEASE_ID=$(python3 -c 'import json; print(json.load(open("RELEASE_MANIFEST.json"))["release_id"])')
export IMAGES_ARCHIVE="images-$RELEASE_ID.tar"
export TARGET_PLATFORM=linux/amd64
python3 -B ops/verify_package.py RELEASE_MANIFEST.json
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml config --quiet
sha256sum -c "$IMAGES_ARCHIVE.sha256"
docker load -i "$IMAGES_ARCHIVE"
python3 -B ops/image_identity.py verify --manifest "images-$RELEASE_ID.manifest.jsonl" --release-id "$RELEASE_ID" --platform "$TARGET_PLATFORM"
python3 ops/preflight.py --env-file "$PRODUCTION_ENV_FILE"
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml up -d db
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml run --rm migrate
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml run --rm -it api python ops/manage.py init-owner --username owner
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml up -d api worker caddy
sh ops/check-release.sh
```

初始化密码在终端交互输入。一次性恢复码另存；不要把终端输出放进公共日志或截图。注册只接受 72 小时内未消费的邀请；预发验收前不发正式邀请。验收后由所有者终端 `python ops/manage.py invite --username owner` 生成邀请，在网页地址后使用 `?invite=<令牌>`；令牌不应经过公开短链或共享记录。

云端启动只检查迁移头和密钥；不会建表、补列或生成 default 账户。迁移失败时 API 不应上线。数据库操作命令必须经过容器 entrypoint；对已运行的容器使用 `docker compose ... exec -T api python entrypoint.py <命令>`，以便从秘密文件组装连接串。

## 备份、独立恢复与定时任务

`ops` 镜像提供与 PG 18 一致的 pg_dump/pg_restore、Python 和 restic，挂载内部网络，通过 `/run/ops` 读取私密配置，不需要暴露数据库端口。其 Python 来自 Debian 基础镜像，须在目标 Docker 环境单独验证依赖锁兼容性。

准备 `OPS_CONFIG_DIR` 中的以下文件，归 UID 10001 所有，权限 0600：

- `pg_service.conf`：`gol_backup` 服务使用 `host=db port=5432 dbname=game_of_life user=gol_app`；`gol_restore` 使用同主机、`dbname=postgres user=gol_admin`，仅用于新的演练库。
- `pgpass`：分别提供上述连接的密码；遵循 libpq 文件格式并转义特殊字符。文件必须 0600，不能依赖会使组权限位开放的 ACL。
- `restic-password`：独立备份仓库的加密口令，另存离线副本。
- `backup.env`：配置 `RESTIC_REPOSITORY` 及远端存储所需的独立受限账户参数。不能使用原服务器本地目录作为唯一仓库。不要把业务 BYOK 或 credential-keys.json 放在此文件中。

`OPS_WORK_DIR` 归 UID 10001，可写，作为备份暂存目录。远端仓库首次 `restic init` 只在明确的新仓库上执行；脚本不自动初始化或删除仓库。

```sh
sh ops/run-backup.sh
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml run --rm --no-deps ops restic snapshots --tag game-of-life
```

备份包通过同一只读 PostgreSQL 快照生成 dump 与逐表行数/哈希清单，另存 dump SHA256；restic 上传、check 成功后保留最近7个自然日及4个自然周各自最新快照的并集。production.env必须设置每套部署生成一次的BACKUP_ID，Compose显式传入RESTIC_HOST；backup和forget都显式--host，forget再按host/tags分组并筛选game-of-life。容器重建、发布版本变化不改变身份，其他部署必须用不同ID。未配置身份时拒绝备份，不回落到临时容器主机名。旧临时host快照需要单独清点/恢复验证/dry-run审核，不自动删除。暂存清理仍只有远端成功且有匹配恢复证据的包才进入删除计划，至少保留最新一个已验证本地包。

独立恢复时，在独立目标数据库服务器准备 `gol_restore` 连接，并通过单独保管的加密密钥校验。下面示例只创建新库，已存在同名库即失败；脚本不使用 `--clean`，不删除任何已有库。

```sh
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml run --rm --no-deps \
  -e RESTORE_SERVICE=gol_restore -e RESTORE_DB=gol_rehearsal_20261009 \
  -e RESTIC_SNAPSHOT=<实际快照ID> \
  -e RESTIC_DUMP_PATH=/backup/<实际备份文件名>.dump \
  -e CREDENTIAL_KEY_FILE=/run/ops/recovered-keys.json \
  ops sh ops/restore-rehearsal.sh
```

`recovered-keys.json` 必须来自另存的离线副本，先以受限权限提供给演练环境。保存命令输出作为恢复证据。上述 Compose 示例仍运行在同一部署网络。异机验收必须把 ops 运行环境和数据库连接移到独立机器，并从独立仓库取回备份，不能把本机恢复冒充异机恢复。校验脚本检查所有表的计数/哈希、迁移头及凭据解密；还必须连接恢复库实际登录、回读记录、核账，记录备份时点与恢复耗时。恢复过程中不要让验证 API 自动写入源库。

定时备份可安装 `deploy/game-of-life-backup.service` 与 `.timer`。发布目录固定 `/opt/game-of-life`，`/etc/game-of-life/backup-runner.env` 只设置 `PRODUCTION_ENV_FILE`。timer 每天03:00执行并补跑漏掉任务。先手动成功，再安装启用并检查退出状态、远端快照和实际恢复。备份unit的OnFailure调用backup-alert.service；monitor.service/timer检测API、worker、备份过期及磁盘，public-probe.service/timer须安装在独立机器。配置参考monitor.env.example，真实HTTPS通知端仅在用户授权后填写；本轮只验证替身，没有发送真实通知。worker心跳阈值300秒并每分钟维护到期挑战；unhealthy不会自动重启或代替外部告警。所有unit仍须目标实测。

## 本轮构建、预检与清理约束

固定源码 ZIP 的全部文件哈希由 RELEASE_MANIFEST.json 校验，`python3 ops/verify_package.py RELEASE_MANIFEST.json` 不依赖Git。镜像构建在Linux构建机按实际架构设置RELEASE_ID/TARGET_PLATFORM，执行 `sh ops/build-images.sh`；脚本串行构建、拒绝覆盖同名档案，导出三个应用镜像及PG。目标机先验SHA再docker load，导入与预检共用 ops/image_identity.py，以原始配置SHA256核对实际安装的标签/平台/应用UID10001:10001，并核对PG身份；不直接比较两端.Id，也不对inspect.Config重序列化求摘要。docker save只流式读取有界JSON，默认总时限300秒并回收子进程，不缓存或落盘整个目标导出TAR。缺字段/未知版本/坏摘要/缺镜像均拒绝，旧v1清单要求从新commit重建，不改写历史包。Dockerfile不是镜像产物。

预检 `python3 ops/preflight.py --env-file "$PRODUCTION_ENV_FILE"` 只输出类别和非秘密摘要。空私有预发可用 `--core-only` 暂缺远端配置，但需要空0600的backup.env供Compose解析；这不满足正式发布。已有数据库卷默认阻断，只在核对用途、备份和目标后使用 `--reviewed-existing-volume`。app-password需owner10001/group实际PG GID/0440，admin-password归PG UID，主密钥归10001，细节见部署清单。迁移后仍需init_db核对头；没有自动修改生产结构。

`ops/check-release.sh` 要求PRODUCTION_ENV_FILE、PUBLIC_HTTPS_URL、RELEASE_ID及RELEASE_GATE_EVIDENCE。基础设施检查通过之后，当前版本24小时内的RR01–RR12必须全PASS，否则非零退出。本轮证据含BLOCKED，不能用于放行邀请。资源采集需新OBSERVATION_FILE，运行 `sh ops/observe-resources.sh` 至少30分钟；实际负载和判定见部署清单。

公网探测同时检查配置首页和同源/service-status。后者经Caddy代理/api/ready，以只读数据库SELECT1返回精确JSON `{"status":"ready"}`，Cache-Control:no-store；API停止或数据库连接失败即PUBLIC_APPLICATION_UNAVAILABLE，首页200不足以通过。内部/api/ready、/api/health仍对公网404。真实通知仍需授权配置接收端；本机测试只向临时HTTPS替身发送类别。目标机API/db停机演练及连续新建ops容器的备份验证步骤见部署清单。

备份只有dump/manifest/hash、restic上传、check和保留流程全部成功才写remote_verified；真实恢复对应snapshot/hash/全表/迁移头证据通过 `python ops/backup_state.py --root /明确暂存根 mark-restored --name 实际包名 --evidence /受限证据.json` 分类。随后 `python ops/backup_state.py --root /明确暂存根 cleanup --keep 2` 默认为dry-run，审核后才加 `--apply`。仅清理名称/路径/哈希都合规且远端和恢复均验证的老包；失败或未分类包保留，至少保留最新一个验证包，拒绝越界和符号链接。不自动递归删目录。

RPO≤24小时、RTO≤4小时是待异机演练证明的目标；现有本地合成恢复不能证明它们。首版无已验收兼容云镜像，失败时关闭入口、停写、保留卷及现场、前滚修复。禁止删卷、清库、强制downgrade或切回无认证旧应用。

## 凭据轮换

在受限操作环境中向 JSON `keys` 增加新版本并修改 `active`，保留旧版本。重启应用以使用新文件，然后运行 `python ops/manage.py rotate-credentials`，它按用户锁串行重加密并递增配置版本。确认旧备份恢复仍可解密后，才根据备份保留周期决定淘汰旧版本。不得仅替换单一主密钥并删除旧 key_id。

## SQLite 真实数据迁移协议

本轮没有读取、预检或迁移真实 game_of_life.db。以下命令需要操作员先获取停写后的**一致冻结副本**；不直接使用仍有写入的源文件。

```sh
python ops/import-sqlite.py --source <明确副本路径> --report <新的预检报告路径>
```

默认只读 dry-run；报告只列行数、ID、异常类别和源文件 SHA256，不输出正文或密钥。17 张表、类型范围、外键、跨用户引用等异常会阻断。已知的判定 35 → 事件 34 悬空情况在合成样本中验证为阻断，**没有自动修复或隔离真实历史**。

正式导入必须在报告获批准后显式提供 `--apply --source-user-id <ID> --target-username <账号> --target-dsn-file <受限DSN文件> --approve-source-sha256 <获准哈希>`，目标仅接受 PostgreSQL 的空白未建档账号。事务内导入，原 ID 对照保留在报告；旧 40 币保留，不补差；旧模型配置不导入，迁入后本人重新绑定。未知自定义锚点、无法解释的审计引用和异常数据必须另行评审。导入前后对照计数、余额、流水与报告，确认成功之前不切换源写入。

## 维护与回退

升级前备份并验证恢复，记录镜像标识、迁移头和保留卷。停 worker 和业务写入后再运行显式迁移；不要通过删除卷或流水解决失败。Compose 文件没有自动 destructive downgrade；迁移 downgrade 明确拒绝删表式回退。

`deploy/Caddyfile.maintenance` 提供 HTTPS 503 维护响应，可用已审核的 Compose 覆盖配置挂载到 `/etc/caddy/Caddyfile` 并启动仅 Caddy；替换前备份原配置并验证 `caddy validate`。维护配置需在目标容器实测，不能假设文件存在就已生效。

如需回退，先停写核账：仅在数据库结构兼容时回退到已知镜像；否则恢复到**新的独立库**，完成登录、记录、余额和密钥校验后再切连接。保留故障库供核对，不自动覆盖源库。任何重新邀请或开放公网都以 [计划验收矩阵](../docs/NEXT_ITERATION_DEV_PLAN.md#11-验收矩阵与交付证据) 的 A 阶段门槛为准。
