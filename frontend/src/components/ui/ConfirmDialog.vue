<script setup>
import { ref, watch, nextTick, onUnmounted, getCurrentInstance } from 'vue'
const props=defineProps({open:Boolean,title:String,busy:Boolean,confirmLabel:String,initialFocus:String})
const emit=defineEmits(['confirm','cancel'])
const titleId='confirm-title-'+getCurrentInstance().uid
const dialog=ref(null);let trigger=null
watch(()=>props.open,async(open)=>{await nextTick();if(open){trigger=document.activeElement;dialog.value?.showModal();if(props.initialFocus){dialog.value?.querySelector(props.initialFocus)?.focus({preventScroll:true});if(dialog.value)dialog.value.scrollTop=0}}else{dialog.value?.close();trigger?.focus()}},{immediate:true})
function cancel(e){e?.preventDefault();if(!props.busy)emit('cancel')}
function trap(e){
 if(e.key!=='Tab')return
 const nodes=[...dialog.value.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(node=>node.getClientRects().length)
 const index=nodes.indexOf(document.activeElement)
 if(!nodes.length){e.preventDefault();dialog.value.focus()}
 else if(e.shiftKey&&(index<=0)){e.preventDefault();nodes.at(-1).focus()}
 else if(!e.shiftKey&&(index<0||index===nodes.length-1)){e.preventDefault();nodes[0].focus()}
}
onUnmounted(()=>{dialog.value?.close();trigger?.focus()})
</script>
<template><dialog ref="dialog" tabindex="-1" class="confirm-dialog" :aria-labelledby="titleId" @keydown="trap" @cancel="cancel"><h2 :id="titleId">{{ title }}</h2><slot /><div class="action-group"><button class="btn" autofocus :disabled="busy" @click="cancel">取消</button><button class="btn primary" :disabled="busy" @click="emit('confirm')">{{ busy?'处理中…':confirmLabel||'确认兑换' }}</button></div></dialog></template>
