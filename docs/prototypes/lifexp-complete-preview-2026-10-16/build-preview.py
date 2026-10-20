from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'daily-review-2026-10-15'
html=(BASE/'index.html').read_text(encoding='utf-8')
html=html.replace('lifexp-routine-demo-20261015-v1','lifexp-complete-preview-20261016-v1')
html=html.replace('<title>LifeXP · 今日与回顾交互示例</title>','<title>LifeXP · 完整体验预览</title>')
for name in ('today','nav','render'):
    html=html.replace('function '+name+'(){','function routine'+name.capitalize()+'(){')
html=html.replace('function confirmPlan(id){','function routineConfirmPlan(id){')
html=html.replace('function plannedRow(plan){','function routinePlannedRow(plan){')
html=html.replace('function startAI(){','function routineStartAI(){')
html=html.replace('function setPage(page){','function routineSetPage(page){')
html=html.replace('交互示例 · 虚构数据，仅存本机','完整体验 Demo · 虚构数据')
html=html.replace('<div class="demo-tools">','<div class="demo-tools"><button class="link-btn" data-nav="preview">审阅本版</button>')
html=html.replace('</style>',(HERE/'preview.css').read_text(encoding='utf-8')+'\n</style>',1)
html=html.replace('<script>','<dialog id="preview-dialog" class="modal" aria-label="操作确认"><div id="preview-dialog-content"></div></dialog>\n<script>',1)
html=html.replace("case 'reset-demo':state=initial();initializePlanner();", "case 'reset-demo':state=initial();initializePlanner();initializePreview(true);")
marker="window.addEventListener('beforeunload'"
pos=html.index(marker)
settings=(HERE/'settings-preview.js').read_text(encoding='utf-8').replace('function handleSettingsAction(action){','function routineHandleSettingsAction(action){').replace('function adminPage(){','function legacyAdminPage(){')
html=html[:pos]+(HERE/'preview.js').read_text(encoding='utf-8')+'\n'+settings+'\n'+(HERE/'admin-preview.js').read_text(encoding='utf-8')+'\n'+html[pos:]
html=html.replace('\nrender();\n</script>','\ninitializePreview();render();\n</script>')
(HERE/'index.html').write_text(html,encoding='utf-8')
(HERE/'_tmp_inline_check.js').write_text(re.search(r'<script>(.*?)</script>',html,re.S).group(1),encoding='utf-8')
print('Built standalone complete preview. No application files changed.')
qa=(BASE/'review-demo.mjs').read_text(encoding='utf-8')
prefix=qa[:qa.index("  await check('initial event")]
(HERE/'check-preview.mjs').write_text(prefix+(HERE/'preview-checks.js').read_text(encoding='utf-8'),encoding='utf-8')
