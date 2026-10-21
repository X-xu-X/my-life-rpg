<script setup>
import { ref,onMounted } from 'vue'
import { api } from '../api'
import { account,storageKey } from '../session'
import { useWorkflowWrite } from '../composables/useWorkflowWrite'
const props=defineProps({id:{type:String,required:true}}),visible=ref(false),prefs=ref(null),error=ref(''),writes=useWorkflowWrite('hint:'+props.id)
const key=()=>storageKey('seen-hint:'+account.value?.login_session+':'+props.id)
onMounted(async()=>{try{prefs.value=await api.flow('/experience-preferences');if(!prefs.value.suppressed.includes(props.id)&&!sessionStorage.getItem(key())){visible.value=true;sessionStorage.setItem(key(),'1')}}catch{}})
async function dismiss(permanent=false){if(permanent){try{prefs.value=await writes.send('/experience-preferences',{expected_version:prefs.value.version,suppressed:[...new Set([...prefs.value.suppressed,props.id])],return_disabled:prefs.value.return_disabled},'PUT')}catch(e){error.value=e.message;return}}visible.value=false}
</script>
<template><aside v-if="visible" class="hint-card"><div><slot/></div><div class="action-group"><button class="text-button" @click="dismiss()">知道了</button><button class="text-button muted" :disabled="writes.busy.value" @click="dismiss(true)">不再提示</button></div><p v-if="error" class="error">{{ error }}</p></aside></template>
