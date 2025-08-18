// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  modules: ['@pinia/nuxt'],
  devtools: { enabled: false },
  build: {
    transpile: ["vueuc"],
  },
  css: [
    'splitpanes/dist/splitpanes.css',
    '@/assets/fonts.css',
    '@/assets/theme.css',
  ],
  vite: {
    ssr: {
      noExternal: ['naive-ui', 'vueuc', '@css-render/vue3-ssr']
    },
    optimizeDeps: {
      // 개발 중 의존성 미리 번들
      include: ['naive-ui', 'vueuc', 'vue-konva', '@css-render/vue3-ssr']
    }
  },
  runtimeConfig: {
    public: {
      apiBase: 'http://localhost:8000', // FastAPI 주소
    }
  }
})