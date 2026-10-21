export function strictDate(value){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false
 const [y,m,d]=value.split('-').map(Number),date=new Date(Date.UTC(y,m-1,d))
 return y>=1900&&y<=2200&&date.getUTCFullYear()===y&&date.getUTCMonth()===m-1&&date.getUTCDate()===d
}
export function shiftDate(value,days){const date=new Date(value+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+days);return date.toISOString().slice(0,10)}
