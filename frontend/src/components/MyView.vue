<script setup>
import { ref, onMounted } from 'vue'
import PageHeader from './ui/PageHeader.vue'
import { api } from '../api'
import { account, clearAccount, setAccount } from '../session'
const error=ref(''),busy=ref(false),message=ref('')
const models=ref(null)
onMounted(async()=>{try{models.value=await api.getLLMConfig()}catch{}})
onMounted(async()=>{try{setAccount(await api.me())}catch(e){error.value=e.message}})
async function neutral(){if(!confirm('13 维各 50 是未评估的游戏起点，初始 80 币。选择后不能再用问卷覆盖。确认开始？'))return;busy.value=true;try{await api.neutralBaseline();account.value=await api.me();message.value='已按未评估基线开始。'}catch(e){error.value=e.message}finally{busy.value=false}}
async function logout(){try{await api.logout();clearAccount()}catch(e){error.value=e.message}}
</script>
<template><div class="reading-page">
  <PageHeader title="我的" :eyebrow="account.username" description="按自己的节奏记录，也慢慢建立游戏基线。" />
  <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="message" class="success" role="status">{{ message }}</p>
  <section v-if="!account.onboarding_completed" class="record-composer"><h2>开启旧规则游戏结算</h2><p>未建档也可以记录、回看和导出。结算前请选择一种基线。</p><div class="action-group"><button class="btn primary" :disabled="busy" @click="neutral">用未评估基线开始</button><RouterLink class="btn" to="/onboarding">通过问卷建立角色</RouterLink></div><p class="muted">中性基线为 13 维各 50、80 启动币，属于游戏起点，不是能力测量。选择后不能再用问卷覆盖。</p></section>
  <section class="my-group"><h2>账号与数据</h2><p class="muted">{{ account.username }} · {{ account.timezone }}</p><nav class="my-links" aria-label="账号与数据"><RouterLink to="/settings">数据导出与备份说明 <span>→</span></RouterLink></nav><button v-if="account.mode==='cloud'" class="btn" @click="logout">退出登录</button></section>
  <section class="my-group"><h2>AI 配置</h2><p class="muted">使用自己的凭据与额度。模型不是记录的前提。</p><p v-for="[group,label] in [['primary','判定'],['aux','辅助']]" :key="group" class="saved-model muted">{{ label }}：<template v-if="models?.[group]?.configured">{{ models[group].provider_id || '本地端点' }} / {{ models[group].model }} · v{{ models[group].config_version || 0 }} · {{ models[group].enabled?'已启用':'已停用' }} · {{ {passed:'已验证聊天连通',failed:'测试失败',stale:'旧验证已失效',untested:'尚未验证'}[models[group].validation?.status] || '尚未验证' }}</template><template v-else>{{ models?'未配置':'读取摘要中' }}</template></p><nav class="my-links" aria-label="AI 配置"><RouterLink to="/settings">模型与密钥 <span>→</span></RouterLink></nav></section>
  <section class="my-group"><h2>个人与游戏设置</h2><nav class="my-links" aria-label="个人与游戏设置"><RouterLink to="/onboarding">角色档案与长期信息 <span>→</span></RouterLink><RouterLink to="/anchors">旧规则锚点与个人校准 <span>→</span></RouterLink><RouterLink to="/challenges">挑战 · 金币 · 商店 · 成就 <span>→</span></RouterLink></nav></section>
  <p class="muted">AI 建议和游戏分数不等于经过验证的精确能力测量。服务器运营方有技术接触数据的能力，建议仅记录你愿意托管的内容。</p>
</div></template>
