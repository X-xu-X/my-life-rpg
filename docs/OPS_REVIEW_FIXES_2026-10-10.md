# 三项运维复审修复

2026-10-10，按用户本轮三项P2反馈修正，基于原未提交A/B及发布准备工作区。原候选 `rr-20261010-22ce20e6-2cee7bc912b7` 及其82项回归证据作为历史保留；新的源码候选标识见 `review/OPS_REVIEW_EVIDENCE_2026-10-10.json` 和 release-artifacts 中对应manifest。没有提交或推送Git，没有读取真实SQLite、连接云机/真实仓库、发送真实通知。无数据库迁移及业务/前端规则变化。

当前固定源码候选 `rr-20261010-22ce20e6-40852598288d`，源码摘要 `40852598288daf084febdf69d2c636445b79b8de96770281155c96380be21b28`。117份应用/前端/迁移及依赖文件与原候选同哈希；本轮12项运维结果单列新证据。ZIP、SHA256、manifest及打包后校验回执位于release-artifacts，镜像仍NOT_BUILT。

| 问题 | 修复 | 本轮实际验证 |
|---|---|---|
| Publishers非空误报 | 仅db的整数PublishedPort>0判定为宿主机映射；0允许；缺失/非法端口数据阻断 | Compose形状样本覆盖null/空/EXPOSE-only、IPv4/IPv6/回环真实映射及混合记录 |
| 临时容器导致保留分组离散 | production.env必填稳定BACKUP_ID，Compose传RESTIC_HOST；backup显式--host，forget同样--host并筛选game-of-life标签、按host,tags分组 | 单元测试换容器身份仍传同一host；真实restic0.14.0本地合成仓库35个快照→9，另部署/另标签两快照完整保留，仓库check通过 |
| 首页200掩盖后端故障 | 监测同时GET首页和同源/service-status；后者经Caddy代理/api/ready，执行只读SELECT1，必须200且JSON严格为status=ready，不缓存 | 真实Caddy2.11.7→隔离Uvicorn/FastAPI→合成SQLite；健康退出0，数据库连接失败和API停止时首页均200但退出2，本机HTTPS假接收器各收到一次PUBLIC_APPLICATION_UNAVAILABLE；恢复后退出0 |

PublishedPort与容器声明端口的差别核对了 [Compose v5.3.1实现](https://github.com/docker/compose/blob/v5.3.1/pkg/compose/ps.go)。稳定身份、host筛选和分组按 [restic官方保留说明](https://restic.readthedocs.io/en/stable/060_forget.html) 实施；Bookworm的 [restic软件包](https://packages.debian.org/bookworm/restic) 为0.14系列，本轮特意以0.14.0便携版验证所用参数。7日＋4周指自然日/周各最新快照的并集，不保证固定11份；本样本实际9份。

真实Caddy校验额外发现并修复两个同文件问题：原request_body单行块解析失败，改为合法多行；原respond/handle排序未按预期阻断内部地址，改用route明确执行顺序。/api/ready、/api/health、docs、openapi.json、redoc在实际HTTPS代理下均404；/service-status可以返回就绪JSON。路由顺序依据 [Caddy handle/route规则](https://caddyserver.com/docs/caddyfile/directives/handle)。check-release.sh同时执行应用探测，并规范首页末尾斜杠。

本轮最终执行 `python -m unittest discover -s tests -p 'test_*ops*.py' -v`，设置已校验的TEST_RESTIC_BIN/TEST_CADDY_BIN：12项通过、零跳过，42.715秒。包含旧迁移/悬空预检2项、运维8项、真实工具2项。Python编译、Compose静态拓扑/身份传递、全部ops shell的sh -n、正式/维护两个Caddyfile实际adapt通过。FastAPI旧on_event弃用警告保留，未改变业务生命周期。

工具为官方便携restic0.14.0/windows-amd64与Caddy2.11.7/windows-amd64；分别核对官方SHA256/SHA512清单才执行。全部运行在本机，新合成仓库和回环HTTPS。Caddy只为测试替换上游/静态目录、绑定回环、使用临时受信任测试证书并关闭自动HTTP跳转；生产路由来自实际deploy/Caddyfile。数据库失败是隔离SQLite只读连接不存在目标的真实连接错误；API停止是真正停止测试Uvicorn，不是伪造200/503。假通知接收器使用临时HTTPS证书，未安装系统CA；测试完均关闭。这里不声称真实PostgreSQL断网、Linux容器或公网证书已经验收。

保留失败原因：初轮真实Caddy因原request_body语法失败；修正后发现内部ready未404，再修正显式路由顺序。两项断言保留，最终通过。工具准备曾误用校验清单格式/算法，静态检查命令曾受PowerShell变量展开影响，均改正后核验；没有执行未校验工具，也没有通过删断言跳过失败。

## 使用及目标机待验收

按修订后的PREFLIGHT_DEPLOY_CHECKLIST配置：BACKUP_ID初次生成一次，跨重建/升级保持，不同部署不同，不能使用RELEASE_ID或临时容器名。backup.env不能替代Compose明确传入的身份。历史随机host快照不会自动改归属或清理，先清点、验证恢复和dry-run，另行审核历史保留。

外部探测机仍填写首页PUBLIC_HTTPS_URL，新脚本自动探测/service-status。该入口只提供数据库连接就绪状态，不替代登录/保存/核账验收，不创建会话、不调用模型。空预发授权后按清单分别停止API/数据库，在独立探测机观察非零及真实通知到达，再恢复；连续三次run-backup（新ops容器）核对身份和保留结果。本轮没有执行这些目标机操作。

源码可继续准备空预发，但镜像NOT_BUILT；Docker实际启动/容器重建、目标30分钟资源、远端保留/异机恢复、真实通知、手机等仍BLOCKED。本轮只重跑运维相关12项；前轮82项不是本轮新结果，应用/前端/迁移文件同哈希证明及历史证据单独记录。当前版机器证据RR01–RR07标NOT_RUN，保留历史通过依据；RR08–RR12完整门槛仍BLOCKED。不能据此开放邀请。

复现工具测试时，先在隔离源码目录创建backups空目录、安装requirements.lock，把TEST_RESTIC_BIN/TEST_CADDY_BIN设为已验证工具绝对路径再执行上述命令。缺少工具会明确skip，不算本轮实测通过。不要指向真实仓库或站点。新源码包与SHA256、manifest、打包后的verification.json均由release-artifacts提供，前版文件不覆盖。
