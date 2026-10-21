<script setup>
import { ref,onMounted } from 'vue'
import EmailRecovery from './EmailRecovery.vue'
import { api } from '../api'
const emit = defineEmits(['authenticated'])
const policy=ref({registration:'invite',email_required:false,mail_ready:false}),email=ref(''),emailToken=ref(''),emailNote=ref('')
onMounted(()=>api.flow('/auth/options').then(value=>{policy.value=value}).catch(e=>{error.value=e.message}))
async function emailAction(path){if(busy.value)return;busy.value=true;try{const result=await api.flow(path,path.endsWith('verify')?{token:emailToken.value}:{email:email.value});emailNote.value=result.message||({sent:'验证邮件已投递，请输入验证码。',verified:'邮箱已验证，可以注册。'}[result.status]||result.status)}catch(e){error.value=e.message}finally{busy.value=false}}
const mode = ref(new URLSearchParams(location.search).has('invite') ? 'register' : 'login')
const username = ref('')
const password = ref('')
const invite = ref(new URLSearchParams(location.search).get('invite') || '')
const recovery = ref('')
const newRecovery = ref('')
const error = ref('')
const busy = ref(false)
async function submit() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    let result
    if (mode.value === 'register') result = await api.register({ username: username.value, password: password.value, ...(invite.value?{invite_token:invite.value}:{}),...(emailToken.value?{email_token:emailToken.value}:{}) })
    else if (mode.value === 'recover') result = await api.recover({ recovery_code: recovery.value, new_password: password.value })
    else result = await api.login({ username: username.value, password: password.value })
    password.value = ''
    if (result.recovery_code) newRecovery.value = result.recovery_code
    else emit('authenticated')
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
function done() {
  newRecovery.value = ''
  const url = new URL(location.href)
  url.searchParams.delete('invite')
  history.replaceState(null, '', url)
  if (mode.value === 'recover') mode.value = 'login'
  else emit('authenticated')
}
</script>
<template>
  <main class="auth-paper">
    <p class="eyebrow">人生手账</p>
    <h1>给今天留一页。</h1>
    <p class="muted">记录小事，慢慢看见自己的积累。</p>
    <section v-if="newRecovery" class="recovery-box" aria-live="polite">
      <h2>请单独保存恢复码</h2><p>只显示这一次。它可用于重设密码，请妥善保管。</p>
      <code class="recovery-code">{{ newRecovery }}</code>
      <button class="btn primary" @click="done">我已保存恢复码</button>
    </section>
    <form v-else @submit.prevent="submit" :aria-describedby="error?'auth-error':undefined">
      <h2>{{ { login: '登录', register: '注册账号', recover: '恢复账号' }[mode] }}</h2>
      <label v-if="mode !== 'recover'">用户名<input v-model="username" autocomplete="username" required minlength="3" maxlength="50" placeholder="3–50个字符，支持中文" /></label>
      <label v-if="mode === 'register'&&policy.registration==='invite'">邀请令牌<input v-model="invite" autocomplete="off" required /></label>
      <p v-if="mode==='register'&&policy.registration==='closed'" class="error">站点已关闭新注册。</p>
      <details v-if="mode==='register'"><summary>注册邮箱{{ policy.email_required?'（须验证）':'（可选）' }}</summary><label>邮箱<input type="email" v-model="email"/></label><button type="button" class="btn" :disabled="busy" @click="emailAction('/auth/email/register-request')">发送验证码</button><label>邮件验证码<input v-model="emailToken" :required="policy.email_required"/></label><button type="button" class="btn" :disabled="busy" @click="emailAction('/auth/email/verify')">验证邮箱</button><p role="status">{{ emailNote }}</p></details>
      <label v-if="mode === 'recover'">恢复码<input v-model="recovery" autocomplete="off" required /></label>
      <label>{{ mode === 'recover' ? '新密码' : '密码' }}<input v-model="password" type="password" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" required minlength="12" maxlength="256" placeholder="至少 12 个字符" /></label>
      <p v-if="error" id="auth-error" class="error" role="alert">{{ error }}</p>
      <button class="btn primary" :disabled="busy">{{ busy ? '请稍候…' : { login: '登录', register: '注册', recover: '重设密码' }[mode] }}</button>
      <div class="auth-switch"><button v-for="key in ['login','register','recover'].filter(key=>key!==mode)" :key="key" type="button" class="btn" :disabled="busy" @click="mode = key; error = ''">{{ {login:'返回登录',register:'注册账号',recover:'忘记密码'}[key] }}</button></div>
    </form><EmailRecovery v-if="mode==='recover'&&!newRecovery"/>
  </main>
</template>
