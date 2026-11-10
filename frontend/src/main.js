import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './design-tokens.css'
import './styles.css'
import './ui-layout.css'
import './daily-use.css'
import './navigation.css'
import './tips.css'
import './record-detail.css'

createApp(App).use(router).mount('#app')
