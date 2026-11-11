<script setup>
import { ref,computed,onMounted } from 'vue'
import { api } from '../api'
import { localDate } from '../session'
import TipLine from './ui/TipLine.vue'
const source=ref([]),error=ref(''),year=ref(Number(localDate().slice(0,4))),month=ref(Number(localDate().slice(5,7))-1)
onMounted(async()=>{try{source.value=await api.getHeatmap()}catch(e){error.value=e.message}})
const monthName=computed(()=>year.value+' 年 '+(month.value+1)+' 月')
const days=computed(()=>{const prefix=year.value+'-'+String(month.value+1).padStart(2,'0')+'-',skip=(new Date(year.value,month.value,1).getDay()+6)%7,count=new Date(year.value,month.value+1,0).getDate();return [...Array(skip).fill(null),...Array.from({length:count},(_,i)=>{const date=prefix+String(i+1).padStart(2,'0');return {date,number:i+1,count:source.value.find(r=>r.date===date)?.count||0}})]})
function move(n){const next=new Date(year.value,month.value+n,1);year.value=next.getFullYear();month.value=next.getMonth()}
</script>
<template><section class="hub-card hub-calendar"><div class="hub-section-heading"><button class="text-button" aria-label="上个月" @click="move(-1)">‹</button><h2>{{ monthName }}</h2><button class="text-button" aria-label="下个月" @click="move(1)">›</button></div><p v-if="error" class="error">{{ error }}</p><div class="hub-calendar-grid"><span v-for="label in ['一','二','三','四','五','六','日']" :key="label" class="hub-weekday">{{ label }}</span><template v-for="(day,i) in days" :key="i"><span v-if="!day"/><RouterLink v-else :to="'/journal?date='+day.date" :aria-label="day.date+'，'+day.count+'条记录'" :class="{'has-record':day.count,'is-today':day.date===localDate()}">{{ day.number }}<span v-if="day.count" class="hub-calendar-dot"/></RouterLink></template></div><TipLine id="calendar.dot" class="hub-small-note" label="不再显示日历圆点说明">有圆点的日期留下过记录；点日期查看当天手账。</TipLine></section></template>
