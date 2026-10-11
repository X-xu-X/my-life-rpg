# 空预发部署清单（2026-10-10）

本清单适配用户已报告的腾讯云上海 Ubuntu 24.04、2 核 2GB、50GB、约 1.9GiB Swap、Docker 29.6.1 / Compose 5.3.1。这些是用户提供的信息，本轮未远程核验。以下服务器命令全部 **待执行**。源码候选包已准备，Linux 镜像尚未构建；不能据此开放正式邀请。

2026-10-10 运维复审修订见 [三项修复及当前候选版](OPS_REVIEW_FIXES_2026-10-10.md)。必须补填稳定BACKUP_ID，并使用同时探测首页与/service-status的新监测脚本。

2026-10-11 镜像协议修订：当前阿里云目标及同版本新包下载步骤以 [GitHub 离线构建指南](GITHUB_OFFLINE_BUILD_GUIDE.md) 为准。导入后以 schema v2 原始配置 SHA256 核验目标已安装镜像；旧 id 清单拒绝并要求重建，不能修改历史交付文件绕过校验。

每次 SSH 操作先确认机器身份。目录固定为 `/opt/game-of-life`，秘密放仓库外。后续升级在停写、备份和审核后替换此目录中的版本，不混用版本目录或移动正在运行的挂载目录。所有密码、主密钥、恢复码和连接串仅保存在用户控制的受限文件，不发送到聊天或截图。

## 1. 最少输入与只读检查

需用户提供：CPU 架构；域名、接入及证书条件；获授权的实施访问方式；独立备份存储方案；独立探测机及通知目标。凭据不需要贴进聊天。域名未就绪时可做私有证书/信任链测试，保持 cloud、HTTPS、Secure Cookie；不要开放 local 模式替代。

位置：服务器现有终端。前提：用户有 Docker 查看权限。命令：

```sh
cat /etc/os-release
uname -m
docker info --format 'arch={{.Architecture}} os={{.OSType}}'
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
ss -lnt
df -h
free -h
```

预期：确认 x86_64→linux/amd64 或 aarch64→linux/arm64，80/443 没有其他业务占用，备份暂存所在分区至少空闲 5GiB。失败停点：架构未知、磁盘不足或端口占用时先定位，不停止未知服务、不重装系统、不开放 Docker socket。

## 2. 固定源码与预构建镜像

位置：有足够内存的 Linux 构建机。前提：取得本轮 ZIP、SHA256 和 manifest；目录是新建的空构建目录。先核对压缩包校验和，再解压。不要把 ZIP 解到真实运行库目录。

```sh
sha256sum -c rr-20261010-*.sha256
unzip rr-20261010-*.zip -d build-source
cd build-source
python3 ops/verify_package.py RELEASE_MANIFEST.json
export RELEASE_ID=$(python3 -c 'import json; print(json.load(open("RELEASE_MANIFEST.json"))["release_id"])')
export TARGET_PLATFORM=linux/amd64
sh ops/build-images.sh
```

`TARGET_PLATFORM` 必须按第 1 步实际架构设置。预期：串行构建三个镜像，生成 `images-$RELEASE_ID.tar`、schema v2 `.manifest.jsonl` 和 `.tar.sha256`，含匹配架构的 PG 镜像。原始配置 config_digest 与诊断 observed_id 分开记录；清单与源码 manifest 分开保存。源码 manifest 的 `image_status=NOT_BUILT` 是打包时事实，后续构建结果见独立 BUILD_RECEIPT.json，不改写原 manifest。

失败停点：任一步非零，不进入目标部署。失败的半成品单独保留以便定位，脚本拒绝覆盖同名档案。当前约 1.6GiB 的阿里云目标机只导入预构建档案，不在目标机重建镜像。

位置：服务器管理员终端。前提：确认 `/opt/game-of-life` 是本轮空预发目录，已有目录或数据库卷必须先核对用途。

```sh
cd /opt/game-of-life
python3 ops/verify_package.py RELEASE_MANIFEST.json
sha256sum -c images-*.tar.sha256
docker load -i images-实际发布ID.tar
export RELEASE_ID=$(python3 -c 'import json; print(json.load(open("RELEASE_MANIFEST.json"))["release_id"])')
export TARGET_PLATFORM=linux/amd64
python3 -B ops/image_identity.py verify --manifest "images-$RELEASE_ID.manifest.jsonl" --release-id "$RELEASE_ID" --platform "$TARGET_PLATFORM"
```

docker load 行将文件名替换为校验通过的实际档案，禁止直接照抄占位符；平台按实际架构填写。预期：四个镜像的原始配置摘要、标签、平台和应用 UID/GID 一致，输出 status=PASS/schema_version=2。外层 observed_id 变化只列诊断角色，不视为配置变化。完整配置不一致返回 IMAGE_CONFIG_DIGEST_MISMATCH，旧协议返回 IMAGE_MANIFEST_REBUILD_REQUIRED，任何失败都停在创建秘密和启动数据库之前。目录中保留本次原样 JSONL 清单。禁止改打 latest 标签覆盖已验收版本。

## 3. 受限配置与秘密

位置：服务器管理员终端。前提：同架构 PG 镜像已导入，确定秘密目录和备份目录。

```sh
cd /opt/game-of-life
export PRODUCTION_ENV_FILE=/etc/game-of-life/production.env
export RELEASE_ID=$(python3 -c 'import json; print(json.load(open("RELEASE_MANIFEST.json"))["release_id"])')
docker run --rm --network none --entrypoint id postgres:18.6-bookworm -u postgres
docker run --rm --network none --entrypoint id postgres:18.6-bookworm -g postgres
```

按 `deploy/.env.production.example` 在仓库外创建 production.env，0600，只写真实 RELEASE_ID、BACKUP_ID、DOMAIN、ACME_EMAIL、SECRETS_DIR、OPS_CONFIG_DIR、OPS_WORK_DIR。BACKUP_ID初次部署生成一次，例如用 `python3 -c 'import uuid; print("gol-"+uuid.uuid4().hex)'` 生成非秘密标识；写入后跨容器重建和版本发布保持不变，不同部署使用不同值，不能用RELEASE_ID或临时容器名。不要设置 DB_URL，不运行展开的 `docker compose config`，只用 `config --quiet`。目录不得是符号链接。

生成两条不同的随机长数据库口令，每条至少 24 字符，分别以独占创建写入 admin-password 和 app-password；生成过程不打印口令。使用已导入 API 镜像的 Python 执行 `ops/manage.py generate-key --output /受限挂载路径/credential-keys.json`；需要挂载新建受限目录并使用 `--entrypoint python`，此操作无需数据库。已有文件必须拒绝覆盖。另存离线密钥副本并核验可取回。

权限必须符合：admin-password 归 PG 镜像实际 UID，0400 或 0600；app-password 归 UID10001、组为实际 PG GID，**0440**；credential-keys.json 归 UID10001，0400 或 0600。应用文件需要 PG 初始化读取，不能把 app-password 一律改成 0600 导致数据库初始化失败。秘密目录仅管理员可遍历，Compose 绑定文件由 Docker 提供，文件本身仍需正确容器权限。

OPS_CONFIG_DIR 和 OPS_WORK_DIR 归 10001，建议 0700；OPS_WORK_DIR 可写。首次只做空库私有预发、尚未配置备份时，也要独占创建一个空的 OPS_CONFIG_DIR/backup.env，0600，以满足 Compose 配置解析；不能因此宣称备份门槛通过。完整备份配置按 ops/README.md 创建 pg_service.conf、pgpass、restic-password、backup.env，各归10001、0600。连接目标固定 db:5432/game_of_life/gol_app，恢复连接 postgres/gol_admin；秘密文件不输出。

预期：文件访问符合容器 UID/GID，主密钥单独保管。失败停点：密钥缺失、权限不对、配置仍有占位符时停止；不把目录设成公开可读，不更换已有密钥以绕过解密失败。

## 4. 只读预检与首次空库启动

位置：`/opt/game-of-life`。前提：步骤 1–3 完成。首次空预发：

```sh
python3 ops/preflight.py --env-file "$PRODUCTION_ENV_FILE" --core-only
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml config --quiet
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml up -d db
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml run --rm migrate
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml run --rm -it api python ops/manage.py init-owner --username owner
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml up -d api worker caddy
```

预期：预检核对源码全部文件哈希、发布标识、已安装镜像原始配置 SHA256/标签/架构/UID、秘密、目标库、磁盘和端口；包括 PostgreSQL 身份，且在执行 PG 镜像取 UID/GID 之前完成。初次发现数据库卷时拒绝继续。已有卷仅在管理员核对确属本应用、已有备份且目标正确后才加 `--reviewed-existing-volume`。`--core-only` 跳过远端备份配置和 ops 镜像检查，保留 api/web/postgres 身份与完整清单结构验证，不跳过认证、HTTPS或密钥；它不能通过正式发布门槛。

Compose的db Publishers中仅内部声明、PublishedPort=0允许通过；实际PublishedPort>0的宿主机映射（含本机回环映射）仍拒绝。这里是禁止数据库映射宿主机的部署策略，不把EXPOSE当作公开端口。

迁移命令必须成功；当前迁移头 `b004_reports`，本轮没有新增迁移。初始化密码交互输入，一次性恢复码单独离线保存，不公开终端录屏。已存在所有者时不要重复初始化。首次启动不会自动导入真实 SQLite。

失败停点：迁移、角色权限、Caddy/TLS、健康检查任一失败，保持入口关闭并保留日志。仅分享脱敏错误类别，禁止展开环境、完整 inspect 或连接串。不能删卷、清库或强制 downgrade。

## 5. 运行、重启及最终发布检查

位置：服务器与独立外部设备。前提：服务已健康，域名/证书可用。

```sh
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml exec -T api python entrypoint.py python -c 'from app.main import init_db; init_db(); print("READY")'
docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml ps
```

须分别执行冷启动、容器重建、计划内主机重启后回读；核验无公开 5432/8000，公网未登录业务返回401，内部health/ready在Caddy下返回404，HTTPS真实签发/续期条件成立。关电脑后用手机蜂窝访问。不能把静态 Caddyfile 校验记成证书或重启实测。

最终设置 PUBLIC_HTTPS_URL、RELEASE_ID 和 RELEASE_GATE_EVIDENCE 后执行 `sh ops/check-release.sh`。证据必须是当前版本、24小时内、RR01–RR12 全 PASS；本轮交付证据含 BLOCKED，**执行会按设计非零退出**。禁止手改状态绕过门槛，先完成对应实际验收。

## 6. 2GB / 30 分钟资源观测（RR09）

位置：目标空预发机。前提：合成双账号，业务无真实敏感数据；镜像已预构建；不调用真实供应商。

```sh
export OBSERVATION_FILE=/var/lib/game-of-life/resource-observation-实际时间.txt
sh ops/observe-resources.sh
```

脚本用独占新文件保存31个一分钟样本。另记操作起止：0–5分钟双账号长文保存和回读；5–10列表/搜索；10–15图表；15–20单worker分析替身（测试适配器不得接入生产）；20–25手写/历史报告；25–30一次完整备份。替身尚未部署时明确标该段 NOT_RUN，不能用空闲观测补足。

记录各容器峰值、主机最小/常规可用内存、Swap趋势/vmstat换页、卷/日志/镜像/暂存空间及OOM/restart。建议阈值：常规段大部分时间 available≥256MiB，零OOM/异常重启，无持续Swap增长/明显换页，保存回读无超时或丢失。未达标先定位峰值/驻留/连接与并发，再评估调整；没有实测不能下升级结论。

## 7. 独立备份、异机恢复与告警（RR10/RR11）

位置：服务器受限终端；异机恢复和公网探测使用另一机器。前提：用户已选定远端仓库、离线密钥及获授权的通知接收端，完整预检通过。

```sh
python3 ops/preflight.py --env-file "$PRODUCTION_ENV_FILE" --reviewed-existing-volume
sh ops/run-backup.sh
```

新远端仓库只经管理员明确确认后初始化；脚本不自动创建或覆盖仓库。备份包含同一快照的 dump/全表manifest/hash；restic backup、check、7日/4周保留全部成功才记 remote_verified。备份/口令/磁盘/通知故障要非零，失败不刷新成功时间。

按 ops/README.md 的恢复命令在**独立机器**取回快照和单独离线密钥，目标只能是新的 `gol_rehearsal_*` 数据库；同名即拒绝。恢复脚本检查全表/迁移/解密，还须实际启动隔离API登录、回读并核账，确认不会连接源库。记录备份时点、上传时点、恢复起止、数据范围与版本，验证 RPO≤24h/RTO≤4h；目前只是目标。

暂存清理先将匹配的真实恢复证据通过 `python ops/backup_state.py --root /明确暂存根 mark-restored --name 实际包名 --evidence /受限证据.json` 分类，再运行 `cleanup --keep 2` 查看计划。审核路径及保留项后才加 `--apply`。失败上传、未恢复分类、名称未知文件全部保留，至少保留最新一个已验证本地包；禁止目录级通配清理。

安装前审阅 deploy 中 backup/monitor/public-probe 的 service/timer：服务器用本地监测，独立探测机用 public-probe；各 WorkingDirectory 固定 `/opt/game-of-life`，私有env在 `/etc/game-of-life`。先手动运行、验证通知实际到达及故障退出状态，再 enable timer。HTTPS webhook仅发送类别，不自动向任何真实联系人发消息。真实通知未验收不能记 PASS；同机探测不能代替外部探测。

外部PUBLIC_HTTPS_URL仍填首页地址，脚本额外GET同源/service-status并要求200及精确JSON `{"status":"ready"}`。该入口由Caddy转发/api/ready，执行只读SELECT1，不读取用户数据/创建会话/调用模型；/api/ready等内部地址继续404。仅首页200、HTML冒充状态或API/数据库不可达均不能算正常。仅此探测也不代替登录/保存的业务验收。

空预发、合成数据且用户授权的目标环境演练：从另一台机器运行probe；服务器分别 `docker compose --env-file "$PRODUCTION_ENV_FILE" -f deploy/compose.prod.yml stop api`、恢复api，再单独stop db。每次首页应仍200，但probe非零且通知到达。随后up -d db、等待健康、up -d api并重读合成记录，确认probe恢复0。禁止在真实业务活动中照抄故障演练；不删除卷。记录实际时间、状态码与接收端结果，本轮本机Caddy演练不能代替此项目标机验收。

空预发远端仓库授权后，连续三次执行run-backup.sh（每次创建新ops容器），保存backup_host与快照列表；它们必须与BACKUP_ID一致。同一天的三次快照按当前自然日/周策略通常只保留最后一份；跨日/周须按真实日期核对7日和4周并集。forget显式筛选当前host及game-of-life标签，不触碰其他部署。旧版临时host快照不会被自动追认或删除；先清点归属、独立恢复证明及forget --dry-run，再单独审核历史保留方案。

## 8. 真机与开放决定

RR12：真实手机360/390级尺寸、软键盘/焦点、2万字、弱网丢响应/重试、账号切换、蜂窝网络、电脑关机后访问，保留操作时间及脱敏结果。桌面 Edge 响应式39页只证明本机视口布局，不等于真机。

最终复审原 T01–T22 及 RR01–RR12，由用户决定是否邀请。当前可以按本清单准备、构建并在授权后部署空预发，不能直接开放正式邀请；真实供应商集成与真实旧库迁移分别授权和验收。

## 9. 停止与回退

首版没有已验收的旧云端镜像。故障时关闭入口/停写，保留卷、失败库、日志和密钥，前滚修复；`deploy/Caddyfile.maintenance` 需经目标环境验证后以已审核覆盖配置挂载，不能假设存在就已生效。只有结构兼容且已验收的认证云端镜像可回退；不得退到旧无认证应用。需要恢复时写新的隔离数据库，验证后再切换，保留原库。不可逆迁移须事先制定前滚或独立恢复方案。
