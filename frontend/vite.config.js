import { resolve } from "path";
import { defineConfig } from "vite";

export default defineConfig({
  root: ".",
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, "index.html"),
        addEvent: resolve(__dirname, "add-event.html"),
        preview: resolve(__dirname, "preview.html"),
        admin: resolve(__dirname, "admin.html"),
        about: resolve(__dirname, "about.html"),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});
