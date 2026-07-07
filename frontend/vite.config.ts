import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const backend = 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/analyze': backend,
      '/graph': backend,
      '/module': backend,
      '/chat': backend,
    },
  },
});
