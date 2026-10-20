<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { account,setAccount,clearAccount } from '../session'
import PageHeader from './ui/PageHeader.vue'
const sessions=ref([])
async function loadSessions(){try{sessions.value=(await api.flow('/auth/sessions')).items}catch(e){error.value=e.message}}
onMounted(loadSessions)
const current=ref(''),password=ref(''),email=ref(account.value?.email||''),token=ref(''),busy=ref(false),error=ref(''),message=ref(''),recovery=ref(''),reauth=ref(false)
async function act(fn){if(busy.value)return;busy.value=true;error.value='';message.value='';try{await fn()}catch(e){error.value=e.message}finally{busy.value=false}}
async function change(){await act(async()=>{const result=await api.flow('/auth/password',{current_password:current.value,new_password:password.value,expected_version:account.value.credentials_version});current.value='';password.value='';recovery.value=result.recovery_code;reauth.value=result.reauthenticate;if(!reauth.value)setAccount(await api.me())})}
async function verify(){await act(async()=>{await api.flow('/auth/email/verify',{token:token.value});token.value='';setAccount(await api.me());message.value='邮箱已验证绑定。'})}
async function logout(){await act(async()=>{await api.logout();clearAccount()})}
</script>
<template><div class="reading-page"><PageHeader title="账号安全" :description="account.username"/><p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
<section v-if="recovery" class="card"><h2>保存新的恢复码</h2><p>旧恢复码已失效。此处只显示一次。</p><code class="recovery-code">{{ recovery }}</code><button class="btn" @click="recovery='';reauth?clearAccount():null">我已保存{{ reauth?'，重新登录':'' }}</button></section>
<template v-else><form class="card" @submit.prevent="change"><h2>主动修改密码</h2><label>当前密码<input type="password" v-model="current" autocomplete="current-password" required/></label><label>新密码<input type="password" v-model="password" autocomplete="new-password" minlength="12" maxlength="256" required/></label><p class="muted">按站点策略撤销其他或全部会话；生成新的恢复码。</p><button class="btn primary" :disabled="busy">修改密码</button></form>
<section class="card"><h2>绑定 / 更换验证邮箱</h2><p>{{ account.email_verified?'已验证邮箱：'+account.email:'尚未绑定已验证邮箱，原恢复码仍可使用。' }}</p><label>邮箱<input type="email" v-model="email" autocomplete="email"/></label><button class="btn" :disabled="busy" @click="act(async()=>{const result=await api.flow('/auth/email/bind-request',{email});message=result.status==='sent'?'验证邮件已投递，请输入邮件中的一次性验证码。':result.message})">发送绑定验证邮件</button><label>邮件验证码<input v-model="token" autocomplete="off"/></label><button class="btn" :disabled="busy" @click="verify">验证并绑定</button><p class="muted">服务未配置时不会报告已发送。验证/找回令牌仅能用于对应用途。</p></section><section class="card"><h2>登录会话</h2><p v-for="session in sessions" :key="session.id">{{ session.current?'当前会话':'其他会话' }} · 登录 {{ session.created_at }} · 最近活动 {{ session.last_seen }}</p><button class="btn" :disabled="busy" @click="act(async()=>{await api.flow('/auth/sessions/revoke-others',{expected_version:account.credentials_version});await loadSessions();message='其他会话已退出'})">退出其他设备</button></section><button class="btn" :disabled="busy" @click="logout">退出登录</button></template></div></template>
