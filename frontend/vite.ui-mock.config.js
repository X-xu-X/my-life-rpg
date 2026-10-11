import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// UI evidence server: fail closed if the browser mock is absent. No API proxy.
export default defineConfig({plugins:[vue(),{name:'deny-unmocked-api',configureServer(server){server.middlewares.use('/api',(_req,res)=>{res.statusCode=599;res.setHeader('Content-Type','application/json');res.end('{"detail":"UI mock required"}')})}}],server:{host:'127.0.0.1',port:15173,strictPort:true}})
