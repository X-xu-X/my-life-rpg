# PostgreSQL 缺省 User 续修交付

日期：2026-10-11。基线：835ebc2f4503b3babadccad05cfc7db5e0eb1209。本文记录提交时的实现及本机测试；最终 Git commit/run/release 以新包 BUILD_RECEIPT.json 为准，真实 Linux 结果以同包两份验证 JSON 为准。

## 修复

ops/image_identity.py 的选择字段模板从直接访问 .Config.User 改为 json(index .Config "User")，兼容真实 Docker CLI 对缺省键的处理，只输出原有五项安全字段，不输出 Config/Env。User 缺省／null／空字符串的比较值为字符串空值；仅字符串和 null 合法，0/false/数组/对象等拒绝。schema v2 清单仍要求 user 是字符串。应用 api/web/ops 仍必须10001:10001，PG显式有效字符串继续与清单及原始配置比对，未忽略PG用户。

配置归一化仅影响用户字段比较；摘要始终对未经修改的原始配置JSON字节计算。缺省、空值、null三种原始配置的摘要各不相同，并均有测试证明。原始摘要／PG身份／平台／标签、防重打标签、有界内存、超时和子进程回收、非零退出、秘密不输出全部保留。

原先的合成矩阵只用显式USER999:999，漏掉了官方PG缺省键；本次保留原矩阵，并加入真实Docker build未写USER的第二套双向矩阵。CI另用 ops/test-containerd-deployment.sh 导入**本次实际部署TAR**到独立Docker29 containerd，使用同一校验器运行完整四角色及core-only。PG来源是构建脚本真实pull的官方postgres:18.6-bookworm，以其RepoDigests和同次配置摘要记录；未用同名scratch替代这一生产导入验证。

## 文件

- ops/image_identity.py：模板与严格可选用户语义。
- tests/test_image_identity.py：新增7项回归，原有17项保留。
- ops/test-image-store-compat.sh：显式＋缺省USER真实CLI双向矩阵，IMAGE_STORE_COMPAT.json追加default_user_matrix。
- ops/test-containerd-deployment.sh（新增）：同次实际四镜像containerd导入验证，产生PRODUCTION_CONTAINERD_VERIFY.json。
- .github/workflows/build-deployment-bundle.yml：生产导入验证成为压缩上传前的硬门槛，receipt追加production_containerd_import=PASS，证据纳入SHA256SUMS。
- docs/GITHUB_OFFLINE_BUILD_GUIDE.md、ops/README.md、本交付：新包说明、证据范围和停点。

## 提交时实测

```powershell
.venv\Scripts\python.exe -B -m unittest tests.test_image_identity tests.test_release_ops -v
git --no-pager diff --check
```

本机32/32 PASS（身份协议24项＋原有运维8项）；覆盖PG缺省/空/null/显式字符串、raw与inspect错误类型、应用三角色缺省及错误用户拒绝、PG空用户情况下配置变化拒绝，并保留全部原有摘要／标签／平台／旧协议／流／超时等回归。shell三个脚本只读语法检查通过。完整Go模板效果不以模拟JSON证明，必须看实际Linux矩阵和生产containerd导入结果。

本机无Docker，因此本机Linux矩阵和真实官方PG导入为NOT_RUN；新Actions成功后必须取得两份实际结果再交付包，不把准备好的脚本记成PASS。真实生产导入报告包括PG的inspect user原值、User键是否存在、清单规范值、原始摘要、官方RepoDigests、实际Docker29版本和driver。测试不启动数据库；目标服务器的导入／预检／迁移／所有者初始化仍为NOT_RUN。

## 停点与部署边界

同次新源码、镜像、manifest、receipt和SHA必须一起使用，新目录保存。现有/home/admin/lifexp-delivery-835ebc2/unpacked及source留作诊断，不替换脚本、不改原包哈希、不重复独占解包或gzip -dk。新包全部SHA、源码哈希、已安装四镜像身份通过后，再按清单创建秘密和初始化空库。任何模板/摘要/平台/应用用户/PG身份错误仍非零停止。保持公网关闭；不清库删卷、不重装降级Docker、不换PG标签或服务器存储后端。

用户已授权本次修复提交、推送及手动新包构建；工作流没有服务器部署动作。正式发布仍须独立的真实备份恢复、资源观测及RR验收。

依据：[OCI Image Configuration](https://github.com/opencontainers/image-spec/blob/main/config.md)将User定义为可选，且可选项null等同缺省；这一语义不会改变内容寻址的原始字节身份。
