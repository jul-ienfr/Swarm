import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { compression } from 'vite-plugin-compression2'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const swarmRuntimeTarget = env.SWARM_DASHBOARD_RUNTIME_URL || 'http://127.0.0.1:5055'
  const legacyApiTarget = env.SWARM_LEGACY_API_URL || 'http://127.0.0.1:5001'

  return {
    base: env.VITE_PUBLIC_BASE || './',
    plugins: [
      vue(),
      compression({ algorithm: 'gzip' }),
      compression({ algorithm: 'brotliCompress' }),
    ],
    server: {
      port: 3000,
      open: true,
      proxy: {
        '/api/swarm': {
          target: swarmRuntimeTarget,
          changeOrigin: true,
          secure: false,
        },
        '/healthz': {
          target: swarmRuntimeTarget,
          changeOrigin: true,
          secure: false,
        },
        '/api': {
          target: legacyApiTarget,
          changeOrigin: true,
          secure: false,
        }
      }
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            'd3': ['d3'],
            'vue-vendor': ['vue', 'vue-router'],
          }
        }
      }
    }
  }
})
