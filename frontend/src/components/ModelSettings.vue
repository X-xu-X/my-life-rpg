<script setup>
import AIChoice from './AIChoice.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api'
import { account, accountEpoch } from '../session'
const groups={primary:'判定模型',aux:'辅助模型'}
const raw=ref(null),forms=ref({}),busy=ref({}),message=ref({})
const epoch=accountEpoch;let alive=true
const current=()=>alive&&epoch===accountEpoch
const help=[
 {name:'DeepSeek',console:'https://platform.deepseek.com/api_keys',models:'https://api-docs.deepseek.com/quick_start/pricing/',docs:'https://api-docs.deepseek.com/'},
 {name:'OpenAI',console:'https://platform.openai.com/api-keys',models:'https://developers.openai.com/api/docs/models',pricing:'https://developers.openai.com/api/docs/pricing',docs:'https://developers.openai.com/api/docs/quickstart'},
 {name:'SiliconFlow',console:'https://cloud.siliconflow.cn/account/ak',models:'https://cloud.siliconflow.cn/models',docs:'https://docs.siliconflow.cn/docs/userguide/quickstart'},
]
async function load(update=true){
 const result=await api.getLLMConfig();if(!current())return
 raw.value=result
 for(const group of Object.keys(groups))if(update===true||update===group){const saved=result[group]||{};forms.value[group]={provider_id:saved.provider_id||'deepseek',enabled:!!saved.enabled,model:saved.model||'',base_url:saved.base_url||'',api_key:''}}
}
function dirty(group){const f=forms.value[group],s=raw.value?.[group];return !!(f&&s&&(f.api_key.trim()||f.enabled!==!!s.enabled||f.provider_id!==(s.provider_id||'deepseek')||f.model!==(s.model||'')||f.base_url!==(s.base_url||'')))}
function status(group){const saved=raw.value?.[group];if(dirty(group))return '有未保存修改 · 请先保存再测试';if(busy.value[group]==='test')return '测试中';if(!saved?.configured)return '未配置';if(!saved.model)return '已绑定 Key · 待填写模型';return ({passed:'聊天连通测试通过',failed:'测试失败',stale:'旧验证已失效',untested:'已保存 · 尚未验证'})[saved?.validation?.status] || '尚未验证'}
function provider(group){const f=forms.value[group];f.base_url=raw.value.providers[f.provider_id]||'';f.api_key=''}
async function save(group,clear=false){
 if(busy.value[group])return
 const f=forms.value[group];message.value[group]=''
 if(!clear&&(!/^[^\s\x00-\x1f\x7f]{1,100}$/.test(f.model)||!f.base_url.trim())){message.value[group]='请填写准确模型 ID（不能含空格）和端点。';return}
 const body=clear?{group,api_key:'',enabled:false}:{group,enabled:f.enabled,model:f.model,base_url:f.base_url,...(account.value?.mode==='cloud'?{provider_id:f.provider_id}:{}),...(f.api_key.trim()?{api_key:f.api_key.trim()}:{})}
 busy.value[group]='save'
 try{await api.putLLMConfig(body);if(!current())return;await load(group);message.value[group]=clear?'已清除密钥并停用。':'配置已保存；尚未验证，不会自动请求供应商。'}
 catch(e){if(current())message.value[group]=e.message}
 finally{if(current())busy.value[group]=''}
}
async function test(group){
 if(busy.value[group]||dirty(group))return
 busy.value[group]='test';message.value[group]=''
 const version=raw.value[group].config_version
 try{const result=await api.testLLMConfig(group,version);if(!current())return;await load(false);message.value[group]=dirty(group)?'测试期间输入已变化；结果只对应已保存版本，请先保存再测试。':result.message}
 catch(e){if(current())message.value[group]=e.message}
 finally{if(current())busy.value[group]=''}
}
onMounted(()=>load().catch(e=>{if(current())message.value.primary=e.message}))
onUnmounted(()=>{alive=false})
</script>
<template><AIChoice/><section class="card settings-section" id="settings-models"><h2 tabindex="-1">模型与 AI</h2>
<p class="muted">个人配置。主组用于事件分析与追问，辅组用于报告；未启用主组时沿用现有辅组回退规则。原文无需模型也能保存。</p>
<p class="muted">保存不会联网。主动测试或分析会发送内容至所选供应商，可能计费；聊天连通通过不保证 JSON 业务能力或永久可用。</p>
<p v-if="account?.mode==='local'&&raw?.env_fallback?.ready" class="muted">本地服务端默认配置：{{ raw.env_fallback.model }}。不是站点托管 AI。</p>
<details class="model-help"><summary>第一次配置？跟着步骤来</summary>
<ol><li>选择供应商。供应商账号与 LifeXP 账号不同。</li><li>在官方控制台创建 Key，只填写在下方密钥框，不发到聊天。</li><li>核对官方模型与价格，复制准确的聊天模型 ID，费用及权限以自己的账号为准。</li><li>保存本组配置，启用后主动测试，查看旁边的结果和修复提示。</li></ol>
<ul><li v-for="entry in help" :key="entry.name">{{ entry.name }}：<a :href="entry.console" target="_blank" rel="noopener noreferrer">控制台 / Key</a> · <a :href="entry.models" target="_blank" rel="noopener noreferrer">模型与价格</a> · <a v-if="entry.pricing" :href="entry.pricing" target="_blank" rel="noopener noreferrer">价格表</a> · <a :href="entry.docs" target="_blank" rel="noopener noreferrer">配置文档</a></li></ul>
<p class="muted">网页聊天免费、赠送额度和零价格 API 是不同概念；不承诺三家全免费或永久免费。官方资料核对：2026-10-18；控制台可能需登录。</p><p class="muted">免费 API 候选可查看 SiliconFlow 本人模型广场当前标记免费的模型；官方说明需实名且有固定限流。不指定具体免费默认 ID，不承诺永久可用。<a href="https://docs.siliconflow.cn/docs/userguide/faqs/rate-limit-and-upgradation" target="_blank" rel="noopener noreferrer">官方免费模型与限流说明</a></p></details>
<section v-for="(label,group) in groups" :key="group" class="model-group">
<h3>{{ label }}</h3><template v-if="raw&&forms[group]">
<p class="saved-model">已保存：{{ raw[group].provider_id || '本地端点' }} / {{ raw[group].model || '未配置' }} · v{{ raw[group].config_version || 0 }} · {{ raw[group].enabled?'已启用':'已停用' }}</p>
<p :data-model-state="group" role="status" aria-live="polite">{{ status(group) }}<span v-if="raw[group].validation?.tested_at"> · {{ raw[group].validation.tested_at }}</span></p>
<p v-if="raw[group].validation?.error_code" class="error">{{ raw[group].validation.error_code }} · {{ raw[group].validation.message }}</p>
<label><input type="checkbox" v-model="forms[group].enabled" /> 启用本组</label>
<div class="form-grid"><label v-if="account?.mode==='cloud'">供应商<select v-model="forms[group].provider_id" @change="provider(group)"><option value="deepseek">DeepSeek</option><option value="openai">OpenAI</option><option value="siliconflow">SiliconFlow</option><option value="custom">其他兼容接口（公网 HTTPS）</option></select></label>
<label>Base URL<input v-model="forms[group].base_url" :readonly="account?.mode==='cloud'&&forms[group].provider_id!=='custom'" /></label><label>模型 ID<input :id="group+'-model'" v-model="forms[group].model" maxlength="100" placeholder="从官方模型页复制准确 ID" /></label></div>
<label>API Key<input :id="group+'-key'" v-model="forms[group].api_key" type="password" autocomplete="new-password" :placeholder="raw[group].configured?'已绑定 · 留空保持；切换供应商需重填':'尚未绑定'" /></label>
<div class="action-group"><button class="btn primary" :disabled="!!busy[group]" @click="save(group)">保存{{ label }}</button><button class="btn" :disabled="!!busy[group]||dirty(group)||!raw[group].configured||!raw[group].enabled" @click="test(group)">测试已保存配置（可能计费）</button><button class="btn" :disabled="!!busy[group]||!raw[group].configured" @click="save(group,true)">清除密钥并停用</button></div>
</template><p v-if="message[group]" class="model-feedback" role="status" aria-live="polite">{{ message[group] }}</p>
</section></section></template>
