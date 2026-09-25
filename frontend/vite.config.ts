import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Em desenvolvimento o Vite serve em 5173 e a API em 8000. O proxy faz o
// navegador ver tudo na mesma origem, o que mantém o cookie de sessão
// funcionando sem afrouxar o SameSite.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
