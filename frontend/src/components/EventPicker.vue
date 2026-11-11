<script setup>
import { ref,onMounted,onBeforeUnmount } from 'vue'
import { api } from '../api'
import { displayEventTime,accountEpoch } from '../session'
const props=defineProps({excludeId:Number,modelValue:Object}),emit=defineEmits(['update:modelValue'])
const query=ref(''),rows=ref([]),error=ref(''),busy=ref(false),cursor=ref(null)
let serial=0,alive=true;const epoch=accountEpoch
async function search(more=false){const token=++serial;busy.value=true;try{const result=await api.flow('/event-options?q='+encodeURIComponent(query.value)+(more&&cursor.value?'&cursor='+cursor.value:''));if(!alive||epoch!==accountEpoch||token!==serial)return;const eligible=result.items.filter(r=>r.id!==props.excludeId&&r.record_kind!=='diary');rows.value=more?[...rows.value,...eligible]:eligible;cursor.value=result.cursor;error.value=''}catch(e){if(token===serial)error.value=e.message}finally{if(token===serial)busy.value=false}}
onMounted(()=>search());onBeforeUnmount(()=>{alive=false;serial++})
</script>
<template><div class="event-picker"><div @keydown.enter.prevent="search()"><label>搜索本人已保存事件<input v-model="query" maxlength="200" placeholder="关键词或摘要"/></label><button type="button" class="btn" :disabled="busy" @click="search()">搜索</button></div><p v-if="error" class="error">{{ error }}</p><p v-if="!query.trim()" class="muted small">只列今天的记录。要关联更早的事，输入关键词再搜。</p><p v-if="modelValue">已选：{{ displayEventTime(modelValue) }} · {{ modelValue.title||modelValue.content.slice(0,80) }} <button type="button" class="btn" @click="emit('update:modelValue',null)">取消选择</button></p><ul class="chart-data"><li v-for="row in rows" :key="row.id"><button type="button" class="btn" @click="emit('update:modelValue',row)">{{ query.trim()?displayEventTime(row)+' · ':'' }}{{ row.title||row.content.slice(0,80) }} · {{ row.is_confirmed?'已入账':'未入账' }}</button></li></ul><button v-if="cursor" type="button" class="btn" :disabled="busy" @click="search(true)">更多事件</button><p v-if="!rows.length&&!busy" class="muted">{{ query.trim()?'没有匹配事件。':'今天还没有可选的记录。' }}</p></div></template>
