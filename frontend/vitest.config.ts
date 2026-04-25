import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vitest/config'

/**
 * Configuração do Vitest. Separada do vite.config.ts para manter a
 * configuração de build sem dependências de teste (jsdom, RTL, etc.)
 * no bundle de produção.
 *
 * Inclui apenas testes do frontend; o backend tem sua própria suíte
 * em pytest. Roda em jsdom para suportar APIs do DOM (window, document).
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Os smoke tests não precisam fazer requests reais ao backend; o
    // setup.ts mocka fetch/axios. Por isso exclui-se qualquer roteamento
    // de rede acidental.
    exclude: ['node_modules', 'dist'],
  },
})
