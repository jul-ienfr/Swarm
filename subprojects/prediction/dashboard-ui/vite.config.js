import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const adapterTarget = env.PREDICTION_DASHBOARD_UI_ADAPTER_URL || 'http://127.0.0.1:5001'
  const runtimeTarget = env.PREDICTION_DASHBOARD_UPSTREAM_URL || 'http://127.0.0.1:3000'
  const legacyApiTarget = env.PREDICTION_LEGACY_API_URL || 'http://127.0.0.1:5001'

  return {
    base: env.VITE_PUBLIC_BASE || './',
    plugins: [vue()],
    server: {
      port: 3000,
      open: true,
      proxy: {
        '/api/polymarket': {
          target: adapterTarget,
          changeOrigin: true,
          secure: false,
        },
        '/api/v1/prediction-markets': {
          target: runtimeTarget,
          changeOrigin: true,
          secure: false,
        },
        '/prediction-markets/dashboard': {
          target: adapterTarget,
          changeOrigin: true,
          secure: false,
        },
        '/api': {
          target: legacyApiTarget,
          changeOrigin: true,
          secure: false,
        }
      }
    }
  }
})
