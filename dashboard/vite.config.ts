import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
    plugins: [react()],
    server: {
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
            },
            '/ws': {
                target: 'ws://localhost:8000',
                ws: true,
            },
        },
    },
    build: {
        rollupOptions: {
            output: {
                manualChunks: {
                    // Vendor chunk - React core
                    vendor: ['react', 'react-dom', 'react-router-dom'],
                    // Charts chunk - Recharts library
                    charts: ['recharts'],
                    // UI chunk - Icons and animations
                    ui: ['lucide-react', 'framer-motion'],
                }
            }
        },
        chunkSizeWarningLimit: 400,
    },
})
