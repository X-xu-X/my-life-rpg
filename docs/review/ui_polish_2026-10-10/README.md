# LifeXP UI 精修证据

本目录使用纯虚构数据，不连接数据库、模型或真实账号。旧 `../ui_2026-10-10/` 不变。

## 已执行范围

- `before/`：修改前工作区（HEAD `22ce20e6117db979df38f5c49cc1c2d7c1694ce8`，包含此前未提交开发）。固定新样本，390×844 / 1440×1000，8 个布局检查，未知 API / 运行异常均为 0。源文件 SHA256 在 `before/checks.json`；不是纯 HEAD 截图。
- `after/`：**中途实现快照，非最终工作区验收**。14 路由 × 5 宽度 = 70 个页面布局检查；131 项检查中 130 PASS、1 FAIL。失败是分页测试重新输入后未聚焦输入框便发送 Enter；已修正测试步骤，尚未复跑。保留 `attempt-1-checks.json`，没有删除失败断言。
- 该次中途快照无未覆盖 API、无收集到的运行异常。所有请求的 method/path 留在 checks.json，故障请求单独由 readMode 控制。
- 最终源码还调整了预览链接间距、旧页键盘操作与字体、报告读取反馈、任务主动作、图表 token / 字体和标签关联。`current-source.json` 标记当前文件摘要及相对中途证据的变化。**不能把中途 PASS 当作这些最终修改的浏览器 PASS。**
- 当前两份既有 Node 行为脚本、26 个 Vue SFC 脚本/模板/样式和 CSS 的静态编译、`git diff --check` PASS，命令输出见 `current-validation.txt`。静态编译不是 Vite 构建。
- 最终构建及浏览器复验受 Windows 沙箱 realpath / 本机端口权限阻止；沙箱外自动审批连续超时。用户选择「先交付代码与当前证据」，本轮停止重试。V12 真机、读屏、真实后端、模型、部署均 NOT_RUN。

## 样本与测量

`fixtures.json` 为测试脚本实际生成的固定样本：2026-10-10、20,000 字符正文、长标题、无空格 URL、13 个虚构维度、固定历史和热力图。测试时浏览器 Date 固定；页面自己的发生日和数据口径不变。字体采用本地系统回退，正常截图浏览器缩放 100%、deviceScaleFactor 1。实际浏览器产品与版本见各阶段 checks.json。

`measurements.json` 的数据来自 DOM getBoundingClientRect / scrollWidth，单位 CSS px。截图保留系统滚动条，因此 390px 视口通常只有 375px 内容可用。200% 文字检查是将各元素原始计算字号一次性乘二，不是缩小浏览器。跨断点与交互检查记录在 checks.json；真机不能由此证明。

可定量比较的新同样本基线：390px 手账首条 **937.53 → 221.06px（中途）**；首页保存按钮底部 **693.91 → 579.36px**，双入口底部 **823.69 → 686.50px**，中途底栏上沿 **780px**。首条 220px 目标中途仍超出 1.06px；最终将预览链接上间距减少 2px，**最终实际高度待复验，未填 PASS**。不得拿旧顾问截图的不同标题长度作这个定量结论。

before 源码以文件摘要标识，没有另存完整源码归档；可复现的是本次固定样本和当前测试工具，不能用当前源码重新声称拍出了原 before。

## 本地复跑

在仓库根目录；使用已安装依赖，不升级锁文件。先保存现有证据副本，避免复跑覆盖中途目录。构建在 `frontend` 目录运行 `npm run build`。

UI 服务器采用 `frontend/vite.ui-mock.config.js`；与普通开发服务器不同，它**没有 API 代理**，任何漏拦截请求在服务器端返回 599，绝不回落后端。

```powershell
# 终端一，frontend 目录
npm run dev -- --config vite.ui-mock.config.js

# 终端二，仓库根目录；只启动独立临时 profile，隐藏窗口
$uiProfile = Join-Path $env:TEMP ('gol_ui_polish_' + [guid]::NewGuid().ToString('N'))
Start-Process -FilePath 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' -WindowStyle Hidden -ArgumentList @('--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-address=127.0.0.1','--remote-debugging-port=19224',('--user-data-dir=' + $uiProfile),'about:blank')
# 等调试端口就绪，再运行
$env:UI_PHASE='after'
node tests/browser_ui_polish.mjs
```

脚本只访问 `http://127.0.0.1:15173`，通过本机 Edge CDP 19224 拦截所有 `/api/` 请求。未知接口响应 599 并计入失败。不读取 .env、旧浏览器状态、生产凭据；仅记录 method/path、合成保存 UUID 与正文指纹，不记录认证或模型 Key 请求体。设置 Key 输入用测试占位值，截图前清空；恢复码是明确虚构样本。测试结束调用 Browser.close；若异常提前退出，需关闭本轮 profile 对应浏览器，勿结束用户日常 Edge。服务器在终端一 Ctrl+C 停止。

本轮收尾：Vite 证据服务器已通过其执行会话 Ctrl+C 停止。两次实际完成的浏览器脚本均调用了 Browser.close；为最终复验另外启动的空白隔离 Edge 尚未确认关闭。沙箱内 CIM 查询被拒，未能安全确定该进程 PID，因此没有结束其他 Edge 进程。其独立临时 profile 前缀为 `gol_ui_polish_`，调试端口为 19224；后续清理须只关闭同时匹配这两项的本轮实例。

最终离线行为检查（仓库根）：

```powershell
node tests/frontend_next.mjs
node tests/frontend_v1_11.mjs
git diff --check
```

`_tmp_ui_compile.mjs` 是本轮静态诊断助手：调用现有 `@vue/compiler-sfc` 编译脚本/模板/样式、解析 CSS；未新增依赖。它不能替代上述构建或浏览器验收。

## 验收映射

详见 `checks.md` 与 `../../UI_POLISH_DELIVERY.md`。当前状态以文件摘要判断；不要把旧构建/中途测量复制成最终 PASS。最终发布输入已改变，旧源码包与发布摘要不代表当前 UI，需后续独立重新生成与复审。
