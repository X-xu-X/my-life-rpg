<script setup>
import { ref } from 'vue'
import { api } from '../api'
const email=ref(''),token=ref(''),password=ref(''),recovery=ref(''),message=ref(''),error=ref(''),busy=ref(false)
async function act(fn){if(busy.value)return;busy.value=true;error.value='';try{await fn()}catch(e){error.value=e.message}finally{busy.value=false}}
</script>
<template><details class="card"><summary>使用已验证邮箱找回</summary><p v-if="error" class="error">{{ error }}</p><p v-if="message" role="status">{{ message }}</p><label>已验证邮箱<input type="email" v-model="email"/></label><button class="btn" :disabled="busy" @click="act(async()=>{const result=await api.flow('/auth/email/recover-request',{email});message=result.message})">发送恢复验证码</button><label>邮件验证码<input v-model="token" autocomplete="off"/></label><label>新密码<input type="password" v-model="password" minlength="12" maxlength="256" autocomplete="new-password"/></label><button class="btn" :disabled="busy" @click="act(async()=>{const result=await api.flow('/auth/email/reset-password',{token,new_password:password});password='';token='';recovery=result.recovery_code;message='密码已修改，请保存新恢复码后返回登录。'})">用验证码重设密码</button><code v-if="recovery" class="recovery-code">{{ recovery }}</code></details></template>
