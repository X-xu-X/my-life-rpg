import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import './design-tokens.css'
import './styles.css'
import './ui-layout.css'

createApp(App).use(router).mount('#app')
