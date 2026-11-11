import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  server: {
    proxy: {
      '/api/v1': 'http://127.0.0.1:5000',
    },
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['coffee-icon.svg'],
      manifest: {
        name: 'Menu Digital Jou Coffee',
        short_name: 'Jou Coffee',
        description: 'Menu digital dan pemesanan Jou Coffee.',
        theme_color: '#294536',
        background_color: '#f7f5f0',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: '/coffee-icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any maskable',
          },
        ],
      },
    }),
  ],
})
