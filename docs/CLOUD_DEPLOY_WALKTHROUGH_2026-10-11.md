# LifeXP 首次上云：分阶段操作手册

日期：2026-10-11（北京时间）。项目：my-life-rpg。当前 HEAD：22ce20e6117db979df38f5c49cc1c2d7c1694ce8，另有大量未提交开发。

已确认域名为 lifexp.cn，注册和解析管理在腾讯云；目标是阿里云杭州的空服务器，无需保留其他网站或数据库。截图套餐为 2 vCPU、2GiB、40GiB、200Mbps 峰值、1 个 IPv4，活动页显示一年 68 元。是否已付款及实例是否创建完成尚未确认。2GiB 是待实测的起步配置，不是容量保证。

本文是操作路线，配合顾问逐段执行；需要服务器输出、备案结果或秘密文件的步骤，应取得实际结果再继续。服务器技术细节以 [预检与部署清单](PREFLIGHT_DEPLOY_CHECKLIST.md) 为准，其开头的腾讯云旧配置由本页已确认的阿里云目标信息替代。不要使用仍描述旧无认证版本的 CLOUD_PREPARATION_GUIDE.md 作为当前执行顺序。

## 1. 现在：创建服务器、开始备案

购买页先切换到“系统镜像”，选择 Ubuntu 24.04 LTS；不要使用截图中的 OpenClaw、Hermes Agent 等应用镜像。地域选择杭州，核对一年期订单与续费价格。若预算允许长期使用 2核4GB，会有更多内存余量；本次 2核2GB 可以先做空库试运行，是否适合正式使用由第 8 步决定。

域名不需要迁移注册商。先在腾讯云确认域名实名认证通过，再到阿里云 ICP 备案系统按实际主体和服务内容办理备案。大陆公网网站应在备案通过后开放；备案审核期间可并行完成代码提交和不对公网开放的部署准备。不要以 IP 或额外端口绕过备案。

官方依据：

- [阿里云轻量服务器备案流程](https://help.aliyun.com/zh/simple-application-server/user-guide/apply-for-an-icp-filing-for-a-domain-name/)
- [阿里云备案与域名相关问题](https://help.aliyun.com/zh/icp-filing/basic-icp-service/support/for-the-record-domain-faq)
- [阿里云轻量使用限制：峰值带宽与备案时长](https://help.aliyun.com/zh/simple-application-server/product-overview/limits)

一年期满足上述文档列明的服务器购买时长要求，仍需在备案系统核验账号、域名和实例资格。备案材料直接交给官方系统，身份证照片和证件号码不发送到聊天。

## 2. 服务器创建后：收集基础信息

执行位置：阿里云实例的远程终端。逐条执行，只查看，不安装、不修改现有服务：

```sh
cat /etc/os-release
uname -m
id
free -h
df -h
docker --version
docker compose version
ss -lnt
```

提供完整输出，以及实例公网 IPv4。输出一般不含密码；不要附带登录密码、SSH 私钥或其他凭据。新系统出现 docker 未找到是正常的，下一步再按已确认系统安装。

顾问据此确认系统、amd64/arm64 架构、管理员权限、空闲磁盘、Swap、80/443 占用和 Docker 状态，再提供适配当前机器的安装命令。不要重装已有实例，也不要随意停止占用端口的未知进程。

## 3. Windows 本地：验证、commit、push

commit 保存到本地 Git，push 上传到 GitHub，服务器部署另行执行。

2026-10-11 的独立检查事实：

- 最新前端生产构建通过：610 个模块，9.27 秒。保留 ECharts 大块提示。
- frontend_next.mjs、frontend_v1_11.mjs 和 git diff --check 通过。
- 对 Git 候选文件和 main 历史 497 个 blob 做常见密钥模式检查；没有发现非合成凭据候选。该模式检查不是完整安全保证。真实数据库和 .env 不在待提交文件中。
- 生产构建浏览器复验使用纯虚构 API、独立隐藏 Edge。第二次完成 149 项检查，148 通过，分页重置失败；第三次补齐 Enter 模拟后，149 项中 147 通过，两项成长页宽屏断点检查失败。没有删除断言或把失败改成通过。两轮均检查 70 个页面布局，未知 API 和收集到的运行异常为零。证据保留在 docs/review/ui_deploy_2026-10-11_attempt2 与 attempt3。
- 上述结果不能证明真实登录、数据库、模型或云部署通过。正式候选仍需定位剩余 UI 失败。
- GitHub 连接器确认目标仓库 X-xu-X/my-life-rpg 为私有仓库，查询时没有远端分支。本机 Git 的远端检查连接被重置；命令行认证也未核验通过。本轮没有 commit 或 push。
- 本轮临时静态页面服务器已停止；完成的浏览器脚本调用了 Browser.close。

执行位置：你电脑上的 PowerShell。

```powershell
Set-Location 'C:\Users\19687\Desktop\游戏人生\work_place\my-life-rpg'
git status --short
git branch --show-current
git remote -v
```

预期：main，origin 指向 https://github.com/X-xu-X/my-life-rpg.git。若 Writer 仍在改代码，先固定一轮交付，避免验证后源码又变化。

需要重新验证时运行以下命令；任一失败都保留输出：

```powershell
node tests/frontend_next.mjs
node tests/frontend_v1_11.mjs
git -c core.safecrlf=false diff --check
Set-Location frontend
npm run build
Set-Location ..
```

当前版本可以做阶段性提交，并明确记录待验状态。正式发布候选应在剩余问题处理和复验后固定。以下暂存范围包括已开发应用、部署工具、测试和文档：

```powershell
git add -- .gitignore .dockerignore .gitattributes app alembic alembic.ini requirements.txt requirements.lock frontend/src frontend/public frontend/index.html frontend/package.json frontend/package-lock.json frontend/vite.ui-mock.config.js deploy ops tests docs
git diff --cached --stat
git diff --cached --name-only
git diff --cached --check
```

逐项检查暂存名单：不得包含 .env、数据库、真实备份、私钥、credential-keys.json、密码文件。不要使用 git add -f 将忽略文件强行加入。按项目约定，一个逻辑单元一个中文提交；若按完整首次上云候选作为交付单元，可使用：

```powershell
git commit -m 'feat: 交付邀请制云端应用候选版本'
```

如果尚未配置命令行 GitHub 登录，使用浏览器交互完成，不把 token 贴给顾问：

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

然后上传 main：

```powershell
git push -u origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short
```

两条 HEAD 哈希应相同，并在 GitHub 页面确认最新提交。若连接失败、认证失败或远端拒绝，停止并提供脱敏错误；不要 force push、不要清空远端、不要关闭 TLS 验证。若远端已有新提交，先比较历史再决定合并方式。

## 4. 固定源码包和安装 Docker

GitHub 上传完成后，在 Windows 项目根目录生成与最新提交对应的源码候选包：

```powershell
.venv/Scripts/python.exe -B ops/package_release.py --output release-artifacts
```

保留命令输出中的发布 ID，以及对应 zip、sha256、manifest、校验回执。不要继续使用 UI 精修前的旧包。release-artifacts 不提交 Git；真实 SQLite 不上传。

服务器端 Docker 安装命令应按第 2 步实际系统结果提供；优先采用 [Docker Ubuntu 官方安装流程](https://docs.docker.com/engine/install/ubuntu/)。只有 Docker 和 Compose 验证可用、磁盘空间充足、架构明确后才继续。

源码包通过 scp 或云控制台文件传输上传；首次部署固定到 /opt/game-of-life。实际 SSH 用户与 IP 先确认，再给可直接复制的传输命令。无需在服务器长期保存你个人 GitHub 的访问 token。

## 5. 构建 Linux 镜像

按 [预检清单第 2 节](PREFLIGHT_DEPLOY_CHECKLIST.md#2-固定源码与预构建镜像) 核对 zip SHA256、解压到新目录、运行 verify_package.py，设置包内真实 RELEASE_ID 和服务器对应 TARGET_PLATFORM，再运行 ops/build-images.sh。

优先使用有足够内存的 Linux 构建机。若只有这台空的 2GiB 服务器，可以在确认空闲内存、Swap 和磁盘后，安排首次串行构建；构建期间先不启动应用或备份。构建失败先定位，不通过重复启动容器碰运气。

预期：api、web、ops、PostgreSQL 的固定版本镜像及镜像清单生成并校验成功。拉取镜像或安装依赖的网络失败与代码失败要分别记录；不使用未知来源的镜像代理或安装脚本。

## 6. 备案通过后：解析域名、准备 HTTPS

在腾讯云 DNSPod 管理 lifexp.cn，新增一条主域名记录：

| 字段 | 值 |
|---|---|
| 主机记录 | @ |
| 类型 | A |
| 线路 | 默认 |
| 记录值 | 已确认的阿里云公网 IPv4 |
| TTL | 保留控制台默认值 |

先只启用 lifexp.cn；不要把 www 解析后就认定 www 的证书和站点也已配置。未配置 IPv6 时不要添加 AAAA 记录。既有冲突记录先核对用途，不盲目删除。

执行位置：Windows PowerShell。

```powershell
Resolve-DnsName lifexp.cn -Type A
```

结果应指向本次服务器。云防火墙允许网站的 TCP 80、443；SSH 只允许需要的管理来源。数据库 5432 和 API 8000 不对公网开放。服务器本机防火墙也要核对，先保障当前管理连接再调整。

Caddy 已配置自动 HTTPS；正常域名解析和外网 80/443 可达是前提，不需要提前购买商业 SSL。参考 [Caddy HTTPS 官方说明](https://caddyserver.com/docs/quick-starts/https)。

## 7. 创建秘密文件、迁移、首次登录

严格依次执行 [预检清单第 3–4 节](PREFLIGHT_DEPLOY_CHECKLIST.md#3-受限配置与秘密)：

1. 在仓库外 /etc/game-of-life 创建生产配置和秘密文件；DOMAIN 填 lifexp.cn，RELEASE_ID 必须对应本包。BACKUP_ID 生成一次后跨升级保留。
2. 分别生成管理员数据库口令、应用数据库口令、凭据加密主密钥，并正确配置容器 UID/GID 和权限。主密钥另存离线副本。
3. 运行只读预检和 compose config --quiet。
4. 先启动数据库，再显式执行 Alembic 迁移。
5. 运行 init-owner 交互创建所有者账号；输入你自己的密码，保存一次性恢复码。
6. 启动 API、worker、Caddy，查看健康状态。

秘密文件生成和权限命令由顾问按实际 PG UID/GID、服务器用户和发布包逐段提供，不复制未替换的占位符。不要将完整展开配置或连接串贴到聊天。不要直接运行本地 start.bat/start.sh 充当云入口。

首次访问 https://lifexp.cn，用初始化的所有者账号登录。先保存虚构测试记录，刷新后回读；退出后验证旧会话不可用。邀请注册和恢复码流程用测试账号验证。此时不导入真实 SQLite。

## 8. 达到正常使用标准

依次完成 [预检清单第 5–9 节](PREFLIGHT_DEPLOY_CHECKLIST.md#5-运行重启及最终发布检查)：

- 未登录业务接口返回 401；不同账号不能查看或修改对方记录。
- 保存、搜索、图表、结算和退出正常；分析任务使用 worker，失败时原文仍保留。
- 本人主动在设置中绑定自己的模型 Key，明确会产生供应商费用后再测试真实模型；凭据不通过聊天交付。
- 容器重建和计划内主机重启后，账号与记录仍存在。
- 在 2GiB 服务器运行代表性负载至少 30 分钟，检查 OOM、Swap、响应及磁盘。未达标再调整或升级，不提前声称够用。
- 配置私有远端自动加密备份、离线主密钥、独立恢复演练与实际告警。购买存储包本身不会完成备份。
- 手机蜂窝网络访问，软键盘、长文、刷新、弱网重试和电脑关机后访问通过。
- 当前前端中未找到备案号展示；备案批准后需按实际号码补充页面备案信息和官方链接，并完成相应复验。
- 当前版本 RR01–RR12 和既有相关验收通过，才能记录正式可用。不得手改失败证据绕过发布门槛。

首次只使用空云库。若需要旧本地记录，另走 ops/README.md 的冻结副本预检、审核、导入和核账流程；保留原库，不直接覆盖。

## 9. 后续更新

每次修改先验证，再在 main 按逻辑单元 commit、push，核对远端 SHA，生成新版本源码包和镜像。云端更新前备份、检查结构兼容性并安排停写；更新后重新登录、保存、回读和检查任务。GitHub 与运行服务器各有自己的状态，推送成功后仍须部署新版本。

失败时保留数据库卷、密钥和日志，先关闭入口、定位并前滚修复；没有已验收兼容旧镜像时不盲目回退。禁止 docker compose down -v、清库、强制 downgrade 或换回无认证应用。
