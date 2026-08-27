import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/setupTests.js",
    // Acotado a src/: por defecto Vitest tambien recogeria e2e/*.spec.js,
    // que son tests de Playwright y usan otro runner.
    include: ["src/**/*.{test,spec}.{js,jsx}"],
  },
});
