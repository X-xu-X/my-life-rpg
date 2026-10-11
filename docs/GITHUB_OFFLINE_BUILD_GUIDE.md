# LifeXP：在 GitHub 构建、在阿里云离线导入

日期：2026-10-11。域名 lifexp.cn；阿里云杭州 Ubuntu 24.04、x86_64，公网 IPv4 为 116.62.38.231。Docker 29.9.0 / Compose 5.6.0 已安装；实际可见内存约 1.6GiB，Swap 2GiB。阿里云官方测试容器运行通过。Docker Hub 直连请求超时；ICP 备案正在审核。

## 1. 构建流程

文件：`.github/workflows/build-deployment-bundle.yml`，页面名称为 `Build deployment bundle`。只允许手动运行 main，使用 GitHub 标准 Ubuntu 24.04 构建机，为服务器构建 linux/amd64 镜像。工作流 token 仅有仓库内容读取权限，checkout 不保留凭据。

流程从运行对应的 Git commit 打包源码，在独立目录解包并校验全部文件，再运行现有 `ops/build-images.sh`。它构建 api、web、ops 和 PostgreSQL 四个部署镜像，核对架构，导出镜像 ID 清单及 TAR，压缩后上传为私有仓库的 Actions artifact。未添加自动部署步骤，也不需要服务器密码、SSH 私钥或模型 API Key。

源码 manifest 原有 `image_status=NOT_BUILT` 保留为打包时事实；成功构建的事实单独写入 `BUILD_RECEIPT.json`。原打包脚本的固定日期前缀及 worktree 描述不能替代当前实际 commit 校验，工作流另行核对 `git_head == GITHUB_SHA`。构建成功不等于登录、数据库恢复、模型调用、负载和正式发布门槛通过。

## 2. 提交与手动运行

在 Windows 项目 PowerShell 中先暂存这两个新文件并检查：

```powershell
git add -- .github/workflows/build-deployment-bundle.yml docs/GITHUB_OFFLINE_BUILD_GUIDE.md
git --no-pager diff --cached --check
```

检查无输出且退出码为 0 后：

```powershell
git commit -m "ci: 添加手动构建云端离线部署包"
git push origin main
```

如果 GitHub 明确提示缺少 workflow scope，使用已安装的 CLI 在浏览器补授权，再重新 push：

```powershell
& 'C:\Program Files\GitHub CLI\gh.exe' auth refresh --hostname github.com --scopes workflow
git push origin main
```

打开仓库 `https://github.com/X-xu-X/my-life-rpg/actions`，左侧选择 `Build deployment bundle`，点击 `Run workflow`，分支选 main，再点击确认运行。若尚未显示该流程，先确认新增文件已经成功 push，再刷新页面。若 Actions 被禁用，查看仓库 Settings → Actions → General 的设置。

工作流使用标准 Linux runner，45 分钟超时，不启用定时或 push 自动运行。私有仓库的分钟数及产物存储使用账号已有配额；GitHub Free 当前包含每月 2,000 分钟、500MB 产物存储额度，额度与其他使用共享，实际费用取决于账号计划、已有用量及付款/预算设置。镜像包大小尚未测得，不能保证它在免费额度内。运行前在账号 Billing and licensing → Usage / Budgets 核对用量；不需要为此购买云端构建服务器或开通更大 runner。

产物只保留 1 天，以减少存储占用；成功后及时下载到电脑。外层 artifact 名称为 `lifexp-linux-amd64-完整提交编号`。构建失败时打开红色步骤的完整日志，保留原始错误；固定基础镜像标签不存在或依赖下载失败时，应交回 Writer 核验，不能静默改用 latest。

## 3. 下载文件与校验顺序

产物包含：

- `rr-*.zip`、对应 `.sha256` 和 `.manifest.json`：本次 Linux 构建实际使用的源码包。
- `images-*.tar.gz`：包含四个部署镜像的压缩归档。
- `images-*.manifest.jsonl`：四个镜像的实际 ID、标签、平台。
- `images-*.tar.sha256`：未压缩 TAR 和镜像 ID 清单的校验和。
- `BUILD_RECEIPT.json`：实际 commit、发布 ID、平台、构建运行编号；部署状态为 NOT_DEPLOYED，发布门槛为 NOT_RUN。
- `SHA256SUMS`：上述交付文件的 SHA256。

使用同一次构建产物中的源码包和镜像包。此前 Windows 本地 `32a3181` 对应源码包只是阶段留档，新增工作流提交后，应以成功构建运行的 commit 和产物为准。Windows 与 Linux 的换行字节可能不同，不能把不同构建的 manifest 和源码混用。

上传路径和 SCP 命令应在下载实际产物、确认 SSH 登录条件后提供，用户不需要在聊天发送登录密码或私钥。上传后在服务器的新交付目录执行顺序为：

1. 校验 `SHA256SUMS`，所有条目必须 OK。
2. 解压 `.tar.gz`，保留压缩档；校验原 `images-*.tar.sha256`。
3. 导入实际镜像 TAR，核对镜像 ID 与平台。
4. 解压同一次源码 ZIP，运行 `ops/verify_package.py`。
5. 按 `PREFLIGHT_DEPLOY_CHECKLIST.md` 创建仓库外的受限配置、密码和主密钥，再进行预检、空库迁移及所有者初始化。

ICP 审核期间保持网站公网关闭，可完成构建、传输及私有预发准备。备案通过后再配置公开访问、HTTPS、备案号展示和真实客户端验收；不要通过公网 IP 或额外端口绕过备案。

## 4. 官方依据

- [GitHub：手动运行工作流](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [GitHub：Actions 配额与计费](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub 官方 checkout](https://github.com/actions/checkout)
- [GitHub 官方 upload-artifact](https://github.com/actions/upload-artifact)
