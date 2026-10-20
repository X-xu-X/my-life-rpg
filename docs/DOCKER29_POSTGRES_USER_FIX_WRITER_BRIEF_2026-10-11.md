# Writer 续修：Docker inspect 对 PostgreSQL 缺省 User 报错

日期：2026-10-11。代码基线：835ebc2f4503b3babadccad05cfc7db5e0eb1209。
交付版本：rr-20261010-835ebc2f-4e50ebc6bac2。本文为审查任务书，尚未修改程序或提交 Git。

## 已确认事实

目标服务器为阿里云杭州 Ubuntu 24.04.2、amd64，Docker 29.9.0，containerd image store。新包外层 ZIP、SHA256SUMS、镜像 TAR/JSONL、223 个源码文件与 build receipt 均校验通过。四个新镜像已导入；verify-archive 为 PASS，目标 verify 为 IMAGE_INSPECT_FAILED。数据库初始化、迁移、所有者初始化尚未执行。

用户逐镜像执行与 INSPECT_FORMAT 相同的命令：api/web/ops 均退出0，平台 linux/amd64，user 为 10001:10001；只有官方 postgres:18.6-bookworm 退出1：

```text
template parsing error: template: :1:105: executing "" at <.Config.User>: map has no entry for key "User"
```

新清单 PostgreSQL 行的 user 为字符串空值。旧版诊断中 meta.get('Config', {}).get('User') 为 null；该 Python get 输出不能单独区分缺字段和显式 null。本次模板错误确认 inspect.Config 内没有 User 键。

## 根因与漏测

`ops/image_identity.py` 的 INSPECT_FORMAT 使用 `{{json .Config.User}}`，将可缺省的 User 当作必有键。在目标 CLI 上缺键导致模板求值失败；inspect_images 丢弃 stderr 后返回 IMAGE_INSPECT_FAILED，尚未执行目标配置摘要的比较。

`ops/test-image-store-compat.sh` 的 postgres 标签是 FROM scratch 合成镜像，显式设置 USER 999:999，因此双向矩阵未覆盖缺省 User。`tests/test_image_identity.py` 的 inspect 测试由 Python 直接产生模拟 JSON，并没有执行真实 Go 模板；其余流式测试多处替换 inspect_images，也不能证明这一模板可处理官方 PG。

OCI Image Configuration 将 User 定为 OPTIONAL，并规定可选项 null 等同缺省。语义归一化仅用于用户字段比较，不得改变配置原始字节或摘要。

- [OCI Image Configuration](https://github.com/opencontainers/image-spec/blob/main/config.md)

## 施工要求

1. 修复选择字段的 inspect 读取方式，支持 User 键缺省、空字符串和 null；仅这些缺省状态按约定归一化为空字符串。错误类型必须拒绝，不能用宽泛 truthy/falsy 转换把0、false、数组或对象静默接受。
2. 保持应用 user 必须为 10001:10001；应用镜像缺省 User 仍应失败。PG 的有效字符串 user 继续与同次 v2 清单及原始配置比较，不能一律忽略 PG 用户。
3. 原始配置 SHA256、标签、平台、PG 身份、前后防重打标签、有界内存、超时、错误非零及秘密不输出全部保留。任何归一化不得重写原始配置 JSON 后再求摘要。
4. 如调整 Go 模板，兼容 classic/containerd 的真实 CLI 返回形态，不输出完整 inspect 或 Config（可能含 Env）。若用内部 JSON 解析方案，输出与异常仍仅限安全字段和受控类别。
5. 加入真实 Docker 缺省 USER 样本，修改矩阵使其覆盖该样本；不只增加模拟 inspect JSON。保留原有显式 UID/GID 样本和两方向跨后端测试。
6. CI 对实际四个生产镜像增加目标类型的 containerd 导入后 verify；其中必须是真实官方 postgres:18.6-bookworm，而非仅同名 scratch 替身。可使用独立临时 DinD，不修改宿主或用户服务器的存储后端。新包 source、manifest、receipt 和镜像仍来自同次构建。
7. 单元测试覆盖 PG User 缺省/空/null、显式用户、错误类型；应用缺省/错误用户拒绝；PG 配置摘要变化即使用户为空也拒绝。补报真实 Linux 验证结果，未执行项明确 NOT_RUN。

## 交付及部署停点

按项目中文 commit 规范交付独立修复，更新交付记录；根据用户授权推送并手动构建新包。重建后保留新旧候选，禁止直接改服务器包内脚本或重写源包校验和来绕过完整性门槛。

目标机现有材料保留在 /home/admin/lifexp-delivery-835ebc2/unpacked，源码在其 source 子目录，未压缩镜像 TAR 已存在。不要重复执行此前的独占解包脚本或 gzip -dk；不要清库、删卷、重装/降级 Docker 或改用其他 PG 标签。修复包经完整验证后再继续创建秘密和数据库初始化。备案审核期间公网入口保持关闭。
