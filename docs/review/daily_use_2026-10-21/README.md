# 2026-10-21 正式日常改版证据

以 ../../DAILY_USE_REDESIGN_DELIVERY_2026-10-21.md 的逐项说明为准。

## 最终有效证据

- final-backend/backend-results.json：163项执行，161通过，2项真实PG未运行；backend-tests.log为完整日志。
- final-backend/captured-model-payloads.json：四用途真实构建并捕获的消息，输入和供应商响应全部合成；检查相应用途存在、其他用途/私密原文和无来源派生内容不出站。
- frontend-build.log：最终Vue构建；已有图表分块体积提示不阻塞构建。
- browser/browser-results.json：109项通过，绑定实际编译产物SHA256。
- browser/runtime-results.json：669次真实本地API、4次假供应商调用，应用/worker异常0；数据库临时合成，未运行生产lifespan。
- browser/api-requests.json、model-payloads.json：实际请求及出站输入；没有CDP Fetch mock API。
- browser/download-directory.json：最终四个真实下载文件的目录；source-manifest.json列源码/产物/下载摘要与24个旧migration未改校验。
- browser/*.png：正式Vue桌面/窄屏、200%核心文本、键盘缩小视口、确认和长页；非原型截图。

浏览器关键按钮通过滚动、elementFromPoint命中校验和实际鼠标事件点击；输入使用受控DOM事件，不宣称真实手机输入法验收。HTTP桥将回环请求转到HTTPS TestClient，只验证真实ASGI业务，生产TLS/浏览器Secure Cookie仍NOT_RUN。

## 过程与边界

baseline.json、initial-status.txt、initial-tracked.patch.gz及initial-files是开工基线，只作差异来源记录，不是待发布代码。first-pass及其他非final日志是探索/修复过程，可能包含失败或旧重复测试计数；不代替最终结果。browser/exploratory包含早期失败的截图和DOM。downloads与downloads-*中只有download-directory.json指定的目录属于最终验收。

所有账号、密码、邮件地址、模型凭据字样、原文和假响应均为隔离夹具。真实PostgreSQL、供应商语义、SMTP收件、手机实机、生产TLS/旧数据及部署均未验。不推送或部署，不碰真实库。

原始差异以gzip逐字节归档，解压后与开工原文件一致；不为消除patch上下文空白而改写原始证据。摘要是本次Windows工作区字节快照，跨系统换行转换会改变文件摘要。
