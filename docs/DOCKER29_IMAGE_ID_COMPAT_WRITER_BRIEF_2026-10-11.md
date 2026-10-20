# Docker 29 镜像身份校验兼容修复任务书

日期：2026-10-11。审查基线：069111acf233e5a6998010818061f5255bb5f677。
角色边界：本文件是审查结论和 Writer 施工要求；本轮没有修改预检代码、构建脚本或运行中的服务器配置。

## 1. 当前部署状态与问题

阿里云杭州 Ubuntu 24.04.2、x86_64，Docker 29.9.0 / Compose 5.6.0。服务器实际可见内存约 1.6GiB，Swap 2GiB；最新截图磁盘可用 29GB、内存 available 约 1.1GiB。lifexp.cn 备案审核中，网站尚未公开。

成功构建版本：`rr-20261010-069111ac-0ed96ac221bd`，GitHub Actions run `38115304330`。外层 ZIP、内层 SHA256SUMS、未压缩镜像 TAR 和 JSONL 的校验均通过。四个镜像均已导入；导入后直接比较 `docker image inspect .Id` 与清单 `id` 的检查失败。数据库初始化、迁移、所有者初始化及应用启动尚未执行。

服务器诊断确认 `Storage=overlayfs`，`driver-type=io.containerd.snapshotter.v1`。四个镜像都满足：清单 expected_id 等于归档中配置 JSON 原始字节的 SHA256；服务器 actual_id 等于 Descriptor.digest；平台为 linux/amd64；RootFS.Layers 与归档配置 rootfs.diff_ids 完全一致。三个应用镜像的 Config.User 为 10001:10001。

| 镜像 | 清单 ID / 归档配置 SHA256（省略 sha256:） | 服务器 ID / Descriptor.digest（省略 sha256:） |
| --- | --- | --- |
| api | fbe3f0e811c4aba9b4251d71f75d86ae65c2d8150b17e4d365b51bce604588ea | 85eac60f74a36ec9f323f89babf37880d91a12f2d6350a02526f6ef7197ab7b3 |
| web | 98fcd65f4ed255c6f3794edf033825d9b7b63c9fd0a5947e2eb02e658303cb9 | eb1b6cfcaad188298906864b6e497fc651e6c699ee3f272eea1ddb1def7226b4 |
| ops | 35cee7bed8c6ed898fb186dbb76845788e4c58aeff89780ec12f69b33357289 | 151f08a5a48e4c79abf0efb327073bf812b4c5ed486e8cb10d3263d07308d6df |
| postgres:18.6-bookworm | 2e182ed2ff8f5d0835353864264437a26dfc542a9a6c677ec495aa54e491627 | b03bc7ca69f193fca7d1ede6c580627f7bb50204a687e82bf14509589c2301f6 |

摘要转录用于定位；实现和验收必须读取实际交付文件及 Docker 输出，不能硬编码本表。

## 2. 已核实的代码缺陷

`ops/build-images.sh` 将构建机 `.Id` 写入 JSONL 的 `id`，没有说明其摘要类型。`ops/preflight.py` 直接以目标机 `meta['Id'] == row['id']` 判断一致；在 classic image store 与 containerd image store 之间导入时会误报 IMAGE_DIGEST_MISMATCH。完整预检和 core-only 的 api/web 检查都会受影响。

上游解释：classic store 使用 image config digest；containerd store 使用 OCI manifest/index digest。它们不能直接互相比对。本次归档 SHA256 和文件层检查成功支持这一诊断，但不能据此跳过后续配置身份校验、数据库验收或正式发布门槛。

- [Moby 上游问题及维护者解释](https://github.com/moby/moby/issues/51934)
- [Docker containerd image store 文档](https://docs.docker.com/engine/storage/containerd/)

## 3. Writer 施工范围

1. 修复构建与预检的镜像身份协议，使用字段含义明确、跨存储后端稳定的原始 image config digest；构建机观察到的 `.Id` 可作为独立诊断字段保留。不得把 OCI manifest/index digest 与 config digest 混为同一类型。
2. 从实际导出的镜像内容读取原始配置 JSON 字节并计算摘要，或采用同等严格、已验证的接口。检查目标机已导入镜像的配置摘要，而不是只检查服务器旁边未变的输入 TAR。不能对 inspect.Config 重序列化来冒充原始配置摘要。
3. 同时验证标签映射、linux/amd64 平台、应用 UID/GID；覆盖 PostgreSQL 的镜像身份及平台。验证失败必须非零退出，缺字段、未知格式、错误摘要、缺失镜像不得被宽松接受。
4. 兼容 classic/containerd 两端。可保留明确检测的旧清单支持；若不支持旧协议，明确拒绝并要求重建。不要通过改写旧 JSONL、SHA256、release receipt、源包 manifest 或跳过校验来放行。
5. 若读取 docker save 流，保持有界内存、进程超时、异常与子进程回收；不把整个镜像 TAR 读入内存，不在此 1.6GiB 目标机重建镜像。不得输出完整 inspect、环境变量或秘密。
6. 更新离线导入指南、预发清单及相关工作流验证步骤，让用户执行的导入校验与 preflight 使用同一协议。源码哈希校验和既有其他预检门槛必须保留。

禁止修改业务功能、登录策略、数据库结构或真实 SQLite；禁止删卷、换 Docker 存储后端、降级或重装 Docker 来掩盖兼容缺陷。不要修改已部署候选文件造成源包哈希失效。

## 4. 必需验证与交付

- 自动化：相同配置在 classic/containerd 不同外层 ID 下通过；配置摘要不一致，即使层、平台和用户相同也失败；错误平台、错误应用用户、错误标签、坏清单、缺失镜像失败。新旧清单策略需有明确测试。
- 实际 Linux：至少实测 classic 构建后导出、containerd 导入并运行完整身份检查；有条件覆盖反向路径。未实际执行的矩阵项明确 NOT_RUN。
- 提供修改文件列表、测试命令和真实结果、兼容策略、失败停点与非秘密示例输出。代码修复完成后在 Windows 用 `git --no-pager diff --check` 检查，按项目习惯中文提交。
- 修复必须进入新的 Git commit，再手动运行 Build deployment bundle，取得匹配源码和镜像的新交付包；不要将旧镜像和新源码清单混用。重新传输的新文件使用新目录，不覆盖当前诊断材料。

## 5. 修复后的部署顺序

新包下载上传 → 校验 SHA256 → 导入及跨后端身份校验 → 核验同版本源码 → 创建仓库外受限秘密与配置 → core-only 预检 → 空数据库启动及迁移 → 所有者初始化 → 私有 HTTPS 与登录验收。备案未通过时保持公网网站关闭；正式发布仍需实际备份恢复、资源观测及其他 RR 门槛，不把构建或本次诊断记成发布 PASS。
