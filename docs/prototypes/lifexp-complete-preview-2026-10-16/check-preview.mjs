import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import http from 'node:http'
import {spawn} from 'node:child_process'
import {fileURLToPath} from 'node:url'
const folder=path.dirname(fileURLToPath(import.meta.url))
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'lifexp-routine-demo-'))
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
const server=http.createServer((req,res)=>{
  if(req.url==='/favicon.ico'){res.writeHead(204);res.end();return}
  if(!['/','/index.html'].includes(req.url)){res.writeHead(404);res.end();return}
  res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});res.end(fs.readFileSync(path.join(folder,'index.html')))
})
await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve)})
const url='http://127.0.0.1:'+server.address().port
const browser=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
  '--headless=new','--disable-gpu','--no-first-run','--no-proxy-server',
  '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
  '--user-data-dir='+profile,'about:blank'
],{windowsHide:true,stdio:'ignore'})
let ws,send
const checks=[],errors=[]
try{
  const active=path.join(profile,'DevToolsActivePort')
  for(let i=0;i<100&&!fs.existsSync(active);i++)await pause(150)
  if(!fs.existsSync(active))throw Error('Isolated browser unavailable')
  const port=fs.readFileSync(active,'utf8').split(/\r?\n/)[0]
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json()
  ws=new WebSocket(pages.find(page=>page.type==='page').webSocketDebuggerUrl)
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})})
  let sequence=0;const waiting=new Map()
  ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const task=waiting.get(message.id);waiting.delete(message.id);message.error?task.reject(Error(message.error.message)):task.resolve(message.result)}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text)})
  send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;waiting.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))})
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value}
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`)
  const fill=(selector,value)=>evaluate(`document.querySelector(${JSON.stringify(selector)}).value=${JSON.stringify(value)}`)
  const change=(selector,value)=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  const writeDiary=async text=>{await click('[data-nav=review]');await fill('#review-note',text);await click('#save-review');await click('[data-nav=today]')}
  const check=async(name,expression)=>{const pass=await evaluate(expression);checks.push({name,pass:!!pass});if(!pass)throw Error(name)}
  const screenshot=async name=>{for(let i=0;i<24&&!await evaluate('document.querySelector("#toast").hidden');i++)await pause(150);const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(folder,name+'.png'),Buffer.from(result.data,'base64'))}
  await send('Page.enable');await send('Runtime.enable')
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false})
  await send('Page.navigate',{url})
  for(let i=0;i<50;i++){if(await evaluate('!!document.querySelector("#event-input")'))break;await pause(100)}
  const shots=[];const shot=async name=>{await screenshot(name);shots.push(name+'.png')};
  const navTo=async page=>{await evaluate(`setPage(${JSON.stringify(page)})`)};
  await check('complete preview initializes fictional data and five main navigation entries',`!!state.preview&&state.date==='2026-10-16'&&document.querySelectorAll('#desktop-nav button').length===5&&state.preview.role==='user'&&recordDays('diary').total===7`);
  await check('today primary actions available without long settings lists',`!!document.querySelector('#event-input')&&!!document.querySelector('.plans-card')&&!!document.querySelector('#care-card')&&!document.querySelector('#model-name')`);
  await shot('desktop-today');
  const initialCount=await evaluate('state.records.length');await click('#save-event');
  await check('empty original is not saved',`state.records.length===${initialCount}`);
  await fill('#event-input','今天专心做了四道练习题，并整理了一页错题。');await change('#save-intent','never');await click('#save-event');
  const newEvent=await evaluate('state.records[0].id');
  await check('no-analysis original saved independently',`state.records[0].analysisIntent==='never'&&state.records[0].content.includes('四道练习题')&&state.records[0].analysisStatus==='idle'`);
  await navTo('handbook');await click(`[data-open-record="${newEvent}"]`);await change('#event-goal','exam');await change('#event-grade','deep');
  await check('saved no-analysis choice shown consistently in detail',`document.querySelector('.detail-block').innerText.includes('只记录 · 不分析')`);
  const beforeAward=await evaluate('balance()');await click('[data-suite=analyze-event]');
  await check('analysis queued without award',`state.records.find(r=>r.id===${JSON.stringify(newEvent)}).analysisStatus==='queued'&&balance()===${beforeAward}`);
  await pause(650);
  await check('main-line effort grade generates illustrative suggestion without settlement',`state.records.find(r=>r.id===${JSON.stringify(newEvent)}).suggestion.bonus===5&&balance()===${beforeAward}`);
  await click('[data-suite=confirm-event]');
  await check('unassessed starting point selected explicitly before award',`document.querySelector('#preview-dialog').open&&!state.preview.neutral`);
  await click('[data-suite=confirm-modal]');await click('[data-suite=confirm-event]');await evaluate('confirmRecord()');
  await check('event confirmation awards once',`balance()===${beforeAward+7}&&state.preview.coinLedger.filter(row=>row.ref===${JSON.stringify(newEvent)}).length===1`);
  await shot('desktop-event-detail');
  await evaluate('openRecord("math")');await click('[data-suite=analyze-event]');await pause(650);await click('[data-suite=confirm-event]');
  const afterMath=await evaluate('balance()'),afterMathAttribute=await evaluate('attributeValue("智力")');
  await navTo('today');await click('[data-plan-action=study][data-completion=done]');await fill('#plan-detail','同一场专项练习，复用已有原文。');await evaluate('document.querySelector("#reuse-plan-record").checked=true');await click('#save-plan-outcome');await click('[data-confirm-plan=study]');
  await check('plan linked to already settled event reuses original award',`state.occurrences['study@2026-10-16'].reusedSettlement&&balance()===${afterMath}&&attributeValue('智力')===${afterMathAttribute}&&document.querySelector('.plans-card').innerText.includes('已关联原入账')`);
  await navTo('today');await click('[data-plan-action=strength][data-completion=missed]');await click('[data-confirm-missed=strength]');await evaluate('openPlanAction("strength","done")');
  await check('missed result locks without supplement modal or extra award',`!document.querySelector('#plan-dialog').open&&state.occurrences['strength@2026-10-16'].resultConfirmed&&state.occurrences['strength@2026-10-16'].status==='missed'&&balance()===${afterMath}`);
  await change('#demo-date','2026-10-19');
  await check('Monday schedule appears',`!!document.querySelector('[data-plan-action=run]')`);
  const beforePartial=await evaluate('balance()');await click('[data-plan-action=run][data-completion=partial]');await fill('#plan-detail','计划跑 30 分钟，实际跑了 15 分钟。');await click('#save-plan-outcome');
  await check('partial result saves fact and suggestion before award',`state.occurrences['run@2026-10-19'].status==='partial'&&!state.occurrences['run@2026-10-19'].settled&&balance()===${beforePartial}`);
  await click('[data-confirm-plan=run]');await evaluate('confirmPlan("run")');
  await check('partial occurrence settles once',`state.occurrences['run@2026-10-19'].settled&&state.ledger.filter(row=>row.key==='run@2026-10-19').length===1&&balance()===${beforePartial+2}`);
  await change('#demo-date','2026-10-20');
  await check('Tuesday has no overdue Monday reminder',`!document.querySelector('[data-plan-action=run]')`);
  await navTo('plans');await check('overall plan list keeps definitions and removes action domain',`state.plans.length===3&&document.querySelector('.planning-layout').innerText.includes('共 3 项')&&!document.querySelector('#new-plan-attribute')`);
  await fill('#new-plan-name','每周三阅读 20 分钟');await fill('#new-plan-goal','阅读习惯');await change('#new-plan-type','weekdays');await evaluate("document.querySelector('input[name=weekday][value=\"3\"]').checked=true");await click('#create-plan');
  await check('new user schedule and associated goal saved without reward',`state.plans.length===4&&state.preview.goals.some(goal=>goal.name==='阅读习惯')&&balance()===${beforePartial+2}`);
  await change('#demo-date','2026-10-21');await navTo('today');await check('new Wednesday plan appears only on scheduled day',`document.querySelector('.plans-card').innerText.includes('每周三阅读 20 分钟')`);await navTo('plans');
  await shot('desktop-plans');await change('#demo-date','2026-10-16');
  await navTo('goals');await click('[data-main-goal=fitness]');
  await check('main-line switch affects future related plans and preserves old awards',`currentGoal().id==='fitness'&&state.plans.find(p=>p.id==='run').main&&!state.plans.find(p=>p.id==='study').main&&balance()===${beforePartial+2}`);
  await click('[data-main-goal=exam]');
  await navTo('review');const diaryOriginal=await evaluate('diaryFacts()[0].content');await click('#start-ai');
  await check('new actual displayed question saved independently',`state.review.sessions.length===2&&state.review.sessions.at(-1).turns[0].state==='asked'`);
  const question=await evaluate('questionList[questionIndex].text');await fill('#ai-answer','昨晚睡了七小时，今天下午精神还可以。');await click('#answer-question');
  await check('AI question and human answer preserve diary original and saved state',`diaryFacts()[0].content===${JSON.stringify(diaryOriginal)}&&state.review.note===${JSON.stringify(diaryOriginal)}&&document.querySelector('.saved-badge').innerText.includes('已保存')&&state.review.sessions.at(-1).turns[0].answer.includes('七小时')`);
  if(await evaluate('!!document.querySelector("#finish-ai")'))await click('#finish-ai');
  await send('Page.reload');for(let i=0;i<50;i++){if(await evaluate('!!document.querySelector("#event-input")'))break;await pause(100)}await navTo('review');
  await check('diary, original AI prompts, user answers and separate analysis survive refresh',`document.querySelector('.review-history').innerText.includes(${JSON.stringify(question)})&&document.querySelector('.review-history').innerText.includes('七小时')&&document.querySelector('.review-history').innerText.includes('AI 分析')&&diaryFacts()[0].content===${JSON.stringify(diaryOriginal)}`);
  await shot('desktop-diary-review');
  await navTo('handbook');await fill('#handbook-search','报错的第一行');await click('[data-suite=search]');
  await check('handbook search excludes AI answer text',`document.querySelector('#handbook-results').innerText.includes('没有找到')`);
  await fill('#handbook-search','');await click('[data-suite=search]');await click('[data-handbook=diary]');
  await check('diary filter and pagination keep page short',`document.querySelectorAll('#handbook-results .record').length===5&&document.querySelector('.pagination').innerText.includes('7 条')`);
  await click('[data-page-step="1"]');await check('second page shows remaining diaries',`document.querySelectorAll('#handbook-results .record').length===2`);await shot('desktop-handbook');
  console.log('Core records, plans, diary and search checks passed.');
  await navTo('settings');await click('[data-model-source=own]');await fill('#model-name','wrong-model-id');await click('[data-suite=test-model]');
  await check('unsaved model edits cannot silently test old configuration',`!document.querySelector('#model-error').hidden&&document.querySelector('#model-error').innerText.includes('先保存')`);
  await click('[data-suite=save-model]');
  await check('saved invalid model is not presented as verified',`state.preview.ai.model==='wrong-model-id'&&state.preview.ai.status==='unverified'&&document.querySelector('#model-saved-status').innerText.includes('尚未验证')`);
  await click('[data-suite=test-model]');await pause(500);
  await check('invalid model failure visible next to controls and input retained',`state.preview.ai.status==='failed'&&document.querySelector('#model-name').value==='wrong-model-id'&&document.querySelector('#model-error').innerText.includes('找不到')`);
  await shot('desktop-model-error');await click('[data-suite=valid-model-example]');await click('[data-suite=save-model]');await click('[data-suite=test-model]');await pause(500);
  await check('validated saved model visible in compact summary',`state.preview.ai.status==='ready'&&document.querySelector('.model-summary').innerText.includes('deepseek-chat')`);
  await shot('desktop-model-settings');await click('[data-model-source=off]');await evaluate('openRecord("project")');await click('[data-suite=analyze-event]');
  await check('AI-off retains original without starting analysis',`document.querySelector('#preview-dialog').open&&state.records.find(r=>r.id==='project').analysisStatus==='idle'`);
  await click('[data-suite=close-modal]');await navTo('settings');await click('[data-model-source=site]');
  await navTo('growth');await click('[data-growth=shop]');const shopBalance=await evaluate('balance()');await click('[data-redeem=tea]');
  await check('shop uses in-page dialog with complete amounts',`document.querySelector('#preview-dialog').open&&document.querySelector('#preview-dialog-content').innerText.includes('30 币')&&document.querySelector('#preview-dialog-content').innerText.includes('${shopBalance-30} 币')`);
  await shot('desktop-redeem-dialog');await click('[data-suite=close-modal]');await check('cancelled redemption does not spend coins',`balance()===${shopBalance}&&state.preview.vouchers.length===0`);
  await click('[data-redeem=tea]');await evaluate('window.qaRedemption=pendingModal');await click('[data-suite=confirm-modal]');await evaluate('window.qaRedemption()');
  await check('same redemption operation creates one voucher and one debit',`balance()===${shopBalance-30}&&state.preview.vouchers.length===1&&state.preview.coinLedger.filter(row=>row.amount<0).length===1`);
  await click('[data-use-voucher]');await check('marking reward enjoyed does not spend coins again',`state.preview.vouchers[0].used&&balance()===${shopBalance-30}`);
  await shot('desktop-shop');await click('[data-growth=achievements]');await click('[data-suite=claim-achievement]');await evaluate('handlePreviewAction("claim-achievement")');
  await check('discovered milestone mock can be claimed only once',`state.preview.claimed.length===1&&balance()===${shopBalance-20}`);
  await check('30-day achievement displays real fictional progress not fabricated completion',`document.body.innerText.includes('7 / 30 天')`);
  await shot('desktop-achievements');await click('[data-growth=stats]');await check('neutral baseline displayed without proficient labels',`document.body.innerText.includes('未评估基线')&&![...document.querySelectorAll('.badge')].some(node=>node.textContent.includes('熟练'))&&document.querySelectorAll('.attribute-row').length===13`);
  await shot('desktop-growth');
  await click('[data-growth=challenge]');await click('[data-suite=accept-challenge]');const challengeBalance=await evaluate('balance()');
  await check('challenge progress counts unique confirmed learning actions across events and plans','learningProgress()===2&&state.preview.challenge.accepted');
  await click('[data-suite=claim-challenge]');await evaluate('handlePreviewAction("claim-challenge")');
  await check('challenge reward mock can be claimed only once',`state.preview.challenge.claimed&&balance()===${challengeBalance+12}&&state.preview.coinLedger.filter(row=>row.id==='challenge-2').length===1`);
  await navTo('export');await evaluate('document.querySelector("#export-ai").checked=true');await click('[data-suite=export-preview]');
  await check('readable export includes paired questions answers and original separately',`document.querySelector('#export-content').innerText.includes('我的原文')&&document.querySelector('#export-content').innerText.includes('AI 提问')&&document.querySelector('#export-content').innerText.includes('我的回答')`);
  await check('readable formats retain event analysis without mixing it into original',`['markdown','html','csv'].every(format=>{const text=buildExport({...exportOptions,format,ai:true}).text;return text.includes(format==='csv'?'eventAnalysis':'AI 事件分析')})`);
  await change('#export-format','json');await evaluate('document.querySelector("#export-game").checked=true');await click('[data-suite=export-preview]');
  await check('JSON archive optionally contains game data and no credentials',`(()=>{const a=JSON.parse(buildExport({...exportOptions,format:'json',game:true,ai:true}).text);return !!a.game&&a.game.coinBalance===balance()&&!a.apiKey&&!a.password&&!a.credentials&&a.records.some(r=>r.review?.length)})()`);
  await check('HTML archive escapes original user markup',`(()=>{state.records.push({id:'escape-qa',date:state.date,kind:'event',title:'安全导出样例',content:'<script>alert(1)</script>'});const text=buildExport({...exportOptions,format:'html'}).text;state.records=state.records.filter(r=>r.id!=='escape-qa');return text.includes('&lt;script&gt;')&&!text.includes('<script>')})()`);
  await check('CSV treats formula-like original as text',`(()=>{state.records.push({id:'csv-qa',date:state.date,kind:'event',title:'=1+1',content:'=1+1'});const text=buildExport({...exportOptions,format:'csv'}).text;state.records=state.records.filter(r=>r.id!=='csv-qa');return text.includes("'=1+1")})()`);
  await shot('desktop-export');const downloadPath=path.join(profile,'downloads');fs.mkdirSync(downloadPath);await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath});await click('[data-suite=export-download]');await pause(700);
  await check('clicking export creates actual local fixture download',`${fs.readdirSync(downloadPath).some(name=>name.endsWith('.json'))}`);
  await navTo('auth');await click('[data-auth-tab=register]');await fill('#auth-email','invalid');await click('[data-suite=auth-submit]');
  await check('registration validation visible without sending email',`!document.querySelector('#auth-error').hidden&&!document.querySelector('#preview-dialog').open`);
  await fill('#auth-email','preview@example.com');await click('[data-suite=auth-submit]');await check('registration flow explicitly simulated email verification',`document.querySelector('#preview-dialog-content').innerText.includes('不会真的创建账号')`);await click('[data-suite=confirm-modal]');
  await check('demo profile updated without persisting passwords',`state.preview.profile.username==='preview_friend'&&!JSON.stringify(state).includes('demo-password-123')`);
  await navTo('security');await click('[data-suite=change-password]');await fill('#password-old','demo-old-pass');await fill('#password-new','short');await fill('#password-confirm','different');await click('[data-suite=confirm-modal]');
  await check('change-password invalid input remains inline without saving secrets',`!document.querySelector('#modal-error').hidden&&!JSON.stringify(state).includes('demo-old-pass')`);await click('[data-suite=close-modal]');await shot('desktop-security');
  await click('[data-suite=logout-devices]');await click('[data-suite=confirm-modal]');await check('device logout mock updates visible session count','state.preview.otherSessions===0&&document.body.innerText.includes("0 个示例会话")');
  await click('[data-auth-tab=forgot]');await click('[data-suite=auth-submit]');await click('[data-suite=confirm-modal]');
  await check('email recovery path does not require the forgotten current password',`!!document.querySelector('#password-new')&&!document.querySelector('#password-old')&&document.querySelector('#preview-dialog-content').innerText.includes('重设密码')`);
  await fill('#password-new','demo-new-password-456');await fill('#password-confirm','demo-new-password-456');await click('[data-suite=confirm-modal]');
  await check('recovery mock completes without storing password',`!document.querySelector('#preview-dialog').open&&!JSON.stringify(state).includes('demo-new-password-456')`);
  await navTo('admin');await check('ordinary identity sees no administrator mutation controls',`!document.querySelector('#notice-title')&&document.body.innerText.includes('日常账号不显示')`);
  await evaluate('handleSettingsAction("toggle-registration")');await check('ordinary demo handler cannot mutate admin registration flag','state.preview.registrationOpen');
  await navTo('preview');await click('[data-role=admin]');
  await check('admin landing uses separate five-item navigation without ordinary pages',`currentPage==='admin'&&document.querySelectorAll('#desktop-nav button').length===5&&![...document.querySelectorAll('#desktop-nav button')].some(button=>['today','handbook','plans','growth','my'].includes(button.dataset.nav))&&document.querySelector('.side-foot').innerText.includes('lifexp_admin')`);
  await check('overview separates ordinary-user and administrator totals',`adminStats().total===4&&adminStats().administrators===1&&adminStats().disabled===1&&document.querySelector('.admin-stats').innerText.includes('不含管理账号')`);
  await shot('desktop-admin');await navTo('handbook');
  await check('admin navigation cannot accidentally render ordinary diary data',`currentPage==='admin'&&!document.querySelector('#handbook-results')&&!document.querySelector('#review-note')`);
  await navTo('admin-users');await check('user list includes registration login and status, but no private record links',`document.querySelectorAll('tbody tr[data-user-id]').length===5&&document.querySelector('.admin-users-table').innerText.includes('最近登录')&&!document.querySelector('[data-open-record]')`);
  await fill('#admin-search','weekend');await click('[data-suite=admin-search]');
  await check('admin username search narrows list',`document.querySelectorAll('tbody tr[data-user-id]').length===1&&document.querySelector('tbody').innerText.includes('weekend_writer')`);
  await click('[data-manage-user=user-weekend]');await evaluate('window.qaUserOperation=pendingModal');await click('[data-suite=confirm-modal]');
  await check('account status change requires reason and leaves state unchanged on error',`!document.querySelector('#modal-error').hidden&&ensureAdminPreview().users.find(user=>user.id==='user-weekend').status==='disabled'&&ensureAdminPreview().audit.length===0`);
  await fill('#admin-user-reason','示例：用户完成说明后恢复使用。');await click('[data-suite=confirm-modal]');await evaluate('window.qaUserOperation()');
  await check('confirmed restore updates count and records one management action',`adminStats().disabled===0&&adminStats().active===4&&ensureAdminPreview().audit.length===1&&ensureAdminPreview().audit[0].target==='weekend_writer'`);
  await fill('#admin-search','');await change('#admin-role-filter','user');await change('#admin-status','active');await click('[data-suite=admin-search]');
  await check('account role and status filters work together','document.querySelectorAll("tbody tr[data-user-id]").length===4');
  await shot('desktop-admin-users');await evaluate('openUserStatus("admin-current")');
  await check('current management account cannot be stopped through user-status control','!document.querySelector("#preview-dialog").open');
  await navTo('admin-site');await fill('#admin-ai-quota','0');await click('[data-suite=admin-save-site]');
  await check('candidate AI quota validates before saving without touching personal model',`!document.querySelector('#admin-site-error').hidden&&ensureAdminPreview().site.dailyQuota===5&&state.preview.ai.source==='site'`);
  await fill('#admin-ai-quota','8');await fill('#admin-site-name','LifeXP 私人试用');await click('[data-suite=admin-save-site]');await click('[data-suite=admin-save-site]');
  await check('candidate site save audited once, separate from user configuration',`ensureAdminPreview().site.dailyQuota===8&&ensureAdminPreview().audit.filter(row=>row.action==='保存站点设置').length===1&&state.preview.ai.source==='site'&&state.preview.ai.model==='XingChenAGI/Xing4.0-29B'`);
  await shot('desktop-admin-site');await click('[data-suite=toggle-registration]');await click('[data-suite=toggle-registration]');
  await check('registration toggle changes recorded with state restored for later demos',`state.preview.registrationOpen&&ensureAdminPreview().audit.filter(row=>row.action==='改变注册开关').length===2`);
  await navTo('admin-notices');await fill('#notice-title','周末一起留一页');await fill('#notice-body','欢迎试用。原文记录和模型分析可以分开进行。');await click('[data-suite=preview-notice]');
  await check('announcement can be previewed before local publishing',`document.querySelector('#preview-dialog-content').innerText.includes('周末一起留一页')&&state.preview.notice.title!=='周末一起留一页'`);await click('[data-suite=close-modal]');await click('[data-suite=publish-notice]');await shot('desktop-admin-notices');await navTo('admin-audit');
  await check('audit includes operator target reason and announcement actions without private content',`document.querySelector('.admin-audit-row').innerText.includes('lifexp_admin')&&document.body.innerText.includes('恢复账号')&&document.body.innerText.includes('发布公告')&&!document.body.innerText.includes(${JSON.stringify(diaryOriginal)})`);
  await shot('desktop-admin-audit');await click('[data-nav=admin-account]');
  await check('admin account settings display management identity only',`document.body.innerText.includes('lifexp_admin')&&!document.body.innerText.includes(state.preview.profile.email)&&!document.querySelector('#model-name')`);
  await shot('desktop-admin-account');await click('[data-admin-back]');
  await check('account back returns to preceding audit page and keeps management identity',`currentPage==='admin-audit'&&state.preview.role==='admin'`);
  await navTo('admin-users');await click('[data-nav=admin-account]');await click('[data-admin-back]');
  await check('account back follows user-list entry rather than always opening overview',`currentPage==='admin-users'&&state.preview.role==='admin'`);
  await evaluate("adminAccountOrigin=null;currentPage='admin-account';render()");await click('[data-admin-back]');
  await check('direct account page without prior navigation falls back to management overview',`currentPage==='admin'&&state.preview.role==='admin'`);
  await send('Page.reload');for(let i=0;i<50;i++){if(await evaluate('!!document.querySelector(".admin-stats")'))break;await pause(100)}
  await check('refresh preserves management landing role counts and audit',`currentPage==='admin'&&state.preview.role==='admin'&&adminStats().active===4&&ensureAdminPreview().audit.length>=5`);
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  for(const [page,name] of [['admin','mobile-admin-overview'],['admin-users','mobile-admin-users'],['admin-site','mobile-admin-site'],['admin-audit','mobile-admin-audit']]){await navTo(page);await check('390px management layout: '+page,'document.documentElement.scrollWidth<=innerWidth');await shot(name);}
  await click('[data-nav=admin-account]');await check('mobile management account security reachable without ordinary account pages',`currentPage==='admin-account'&&!!document.querySelector('[data-suite=change-password]')&&!document.querySelector('#model-name')`);
  await check('mobile account back button fits viewport and has touch target',`document.documentElement.scrollWidth<=innerWidth&&document.querySelector('[data-admin-back]').getBoundingClientRect().height>=44`);
  await shot('mobile-admin-account');await click('[data-admin-back]');
  await check('mobile back returns to preceding management page',`currentPage==='admin-audit'&&state.preview.role==='admin'`);
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
  await navTo('preview');await click('[data-role=user]');await navTo('today');await check('new local announcement appears for normal preview identity',`document.querySelector('.announcement').innerText.includes('周末一起留一页')`);
  await check('leaving management clears account return destination','adminAccountOrigin===null');
  await click('[data-suite=dismiss-notice]');await check('dismissed announcement no longer repeats','!document.querySelector(".announcement")');
  await navTo('preview');await click('[data-decision=records][data-choice-value="接受这版"]');await fill('#preview-feedback','想先确认页面，再写开发文档。');await click('[data-suite=save-feedback]');
  await check('review choices stored locally with no writer dispatch',`state.preview.decisions.records==='接受这版'&&state.preview.feedback.includes('先确认')`);
  await shot('desktop-preview-guide');
  console.log('Models, rewards, exports and candidate account/admin flows passed.');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  for(const [page,name] of [['today','mobile-today'],['handbook','mobile-handbook'],['review','mobile-diary'],['plans','mobile-plans'],['settings','mobile-model'],['growth','mobile-growth'],['export','mobile-export'],['my','mobile-my'],['auth','mobile-auth']]){
    await navTo(page);await check('390px whole-page layout: '+page,'document.documentElement.scrollWidth<=innerWidth');await shot(name);
  }
  await navTo('growth');await click('[data-growth=stats]');await shot('mobile-growth-stats');
  await send('Emulation.setDeviceMetricsOverride',{width:360,height:800,deviceScaleFactor:1,mobile:true});await navTo('plans');await check('360px plan layout and action controls remain in viewport','document.documentElement.scrollWidth<=innerWidth');
  await send('Emulation.setDeviceMetricsOverride',{width:768,height:1024,deviceScaleFactor:1,mobile:true});await navTo('settings');await check('768px tablet layout fits','document.documentElement.scrollWidth<=innerWidth');await shot('tablet-model');
  await send('Page.reload');for(let i=0;i<50;i++){if(await evaluate('!!document.querySelector("#event-input")'))break;await pause(100)}
  await check('complete preview refresh retains awards vouchers feedback and separate diaries',`state.preview.vouchers.length===1&&state.preview.claimed.length===1&&state.preview.feedback.includes('先确认')&&recordDays('diary').total===7`);
  await check('all source interactions remain local with CSP blocking API traffic',`document.querySelector('meta[http-equiv="Content-Security-Policy"]').content.includes("connect-src 'none'")&&!document.querySelector('input[type=password]')`);
  if(errors.length)throw Error('Runtime exceptions: '+errors.join(';'));
  const result={status:'PASS',validatedAt:new Date().toISOString(),scope:'Complete fictional local preview. No real authentication, emails, APIs, cloud, migrations, or writer dispatch. Browser simulations do not prove backend security or model quality.',checks,runtimeErrors:errors,screenshots:shots};
  fs.writeFileSync(path.join(folder,'qa-summary.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({status:result.status,checks:checks.length,screenshots:shots.length,runtimeErrors:errors}));
}catch(error){fs.writeFileSync(path.join(folder,'qa-summary.json'),JSON.stringify({status:'FAIL',checks,runtimeErrors:errors,error:error.message},null,2));throw error;}
finally{if(send)await send('Browser.close').catch(()=>{});ws?.close();browser.kill();await new Promise(resolve=>server.close(resolve));}
