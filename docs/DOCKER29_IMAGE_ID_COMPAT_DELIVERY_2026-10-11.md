# Docker 29 镜像配置身份修复交付

日期：2026-10-11。修复基线：069111acf233e5a6998010818061f5255bb5f677。本文记录提交时的实现与本机验证；新 commit、Actions run 与实际交付版本以同次 BUILD_RECEIPT.json 为准，Linux 矩阵以 IMAGE_STORE_COMPAT.json 为准。

## 修改范围

| 文件 | 结果 |
| --- | --- |
| ops/image_identity.py（新增） | 共用 schema v2 协议，原始配置 SHA256、标签／平台／用户约束、目标已安装镜像流式校验 |
| ops/build-images.sh | 先导出 TAR，再核对归档与已安装镜像并生成新清单，不再把 .Id 当稳定身份 |
| ops/preflight.py | 完整与 core-only 共用协议，加入 PG 身份；身份失败停在执行 PG 镜像之前 |
| tests/test_image_identity.py（新增） | 17 项协议、真实子进程流、超时／内存及预检接入测试 |
| ops/test-image-store-compat.sh（新增） | 临时 Linux runner 的两个独立 Docker 29 DinD 容器，classic→containerd 与反向合成镜像实测 |
| .github/workflows/build-deployment-bundle.yml | 单元及跨存储矩阵先行，实际部署镜像分别核对归档与已安装身份，附矩阵报告和协议 receipt 字段 |
| docs/GITHUB_OFFLINE_BUILD_GUIDE.md、docs/PREFLIGHT_DEPLOY_CHECKLIST.md、docs/CLOUD_DEPLOY_WALKTHROUGH_2026-10-11.md、ops/README.md | 同版本新目录导入顺序、共用校验命令、旧清单拒绝及失败停点 |

没有修改业务、认证、迁移或真实数据库；没有改写旧候选、旧 JSONL、SHA256、receipt 或源码 manifest。

## 协议与兼容策略

每个 JSONL 行严格包含 schema_version=2、release_id、role、image、config_digest、observed_id、platform、user，共四个角色 api/web/ops/postgres。config_digest 是 docker save 中配置 JSON **原始字节**的 SHA256，校验其内容寻址文件名。observed_id 是构建端 .Id，仅作独立诊断，不与 config_digest 混用。传统 `<digest>.json` 和 OCI `blobs/sha256/<digest>` 布局均支持；需要明确 manifest.json 标签映射。缺字段、重复角色／键、未知版本／格式、无效摘要、错误标签、配置缺失等均拒绝。

部署 verify 不接受输入 TAR 参数，必须实际 inspect 并流式 docker image save 已安装标签；校验前后复查观察字段，发现重打标签即拒绝。应用 User 必须为 10001:10001，PG 同样核对配置摘要／平台／User。core-only 选择 api/web/postgres，但仍要求合法完整四行清单。归档离线命令 verify-archive 明确报告 installed_images=NOT_CHECKED，不能替代目标 verify。

旧版 id/platform/tags 清单不支持，返回 IMAGE_MANIFEST_REBUILD_REQUIRED，必须从含修复的新 commit 手动构建新包。不能用 create 在目标旧档案旁生成清单来绕过重建；create 仅用于构建端导出新包。原候选 rr-20261010-069111ac-0ed96ac221bd 保留诊断用途，不能拼接新源码继续部署。

镜像 TAR 不整体读入内存、不解包到文件系统。只读取有界 JSON（单项4MiB、合计32MiB、清单64KiB、最多4096个归档头），层数据流式跳过，PAX/GNU 隐含元数据也限长并拒绝 sparse 格式。save 默认300秒总时限；失败／超时杀死并等待子进程，stderr 丢弃，CLI 只输出受控类别，不输出完整 inspect 或配置。目标机无须重建镜像。

## 本机真实验证

在 Windows 项目目录执行：

```powershell
.venv\Scripts\python.exe -B -m unittest tests.test_image_identity tests.test_release_ops -v
git --no-pager diff --check
```

结果：25 项通过（17 项新协议＋8 项既有运维回归）。覆盖不同外层 ID 通过；配置变化但层／平台／User 相同拒绝；PG 配置变化拒绝；错误平台／用户／标签、缺镜像、坏清单／旧协议拒绝；原始字节而非重序列化；创建时归档与实际安装一致；core-only 边界；校验失败阻止 PG 镜像执行；真实子进程超时回收；24MiB 合成层跳过时 Python 分配峰值低于2MiB；恶意扩展归档头被限长；CLI 非零且不泄露输入。

Shell 语法检查通过（使用当前安装的 Git runtime sh，`-n ops/build-images.sh ops/test-image-store-compat.sh`）。沙箱最初阻止 MSYS 初始化，沙箱外只读检查成功。GitHub CLI 登录在沙箱内误报无效，沙箱外 keyring 登录有效且具 repo/workflow scope。

额外执行 tests.test_ops_next：其中迁移合成样本通过；SQLite 导入回归被沙箱 Path.resolve 对其新合成文件返回 WinError5 阻断，不能记整组通过。未读取真实 SQLite，也未为本次协议修改该导入逻辑。

本机无 Docker，WSL 查询返回 E_ACCESSDENIED，因此本机 Linux classic→containerd／反向均为 NOT_RUN。工作流已加入两方向真实 Linux 矩阵，必须以成功 run 中 IMAGE_STORE_COMPAT.json 的实际版本和结果作交付证据。该测试使用合成 scratch 镜像，包括仅用于协议测试的 PG 标签；实际四个生产镜像另由 build/verify-archive/verify 检查。它不证明目标服务器预检、PG 初始化、备份恢复或正式发布通过。

## 非秘密输出与失败停点

不同外层 ID、同配置的示例（合成测试）：

```json
{"status":"PASS","schema_version":2,"identity_type":"raw-image-config-sha256","platform":"linux/amd64","roles":["api","web","ops","postgres"],"outer_id_changed":["api","web","ops","postgres"]}
```

配置变化：`{"status":"FAIL","category":"IMAGE_CONFIG_DIGEST_MISMATCH"}`，退出2；旧清单：`{"status":"FAIL","category":"IMAGE_MANIFEST_REBUILD_REQUIRED"}`，退出2。任何身份失败都停在创建秘密、数据库初始化、迁移和所有者初始化之前。源码哈希、秘密权限、空卷审核、磁盘／端口及备份／发布门槛仍保留。矩阵／构建失败则没有新的可部署包，不改旧档案救场。

新包需匹配实际修复 commit，在服务器**新目录**校验 SHA256SUMS、原 TAR 校验和、源码全部哈希，再导入并验证已安装配置，随后按预检清单推进。备案未通过时公网网站保持关闭，备份恢复和 RR 正式发布门槛仍待独立实测。
