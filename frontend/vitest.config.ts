import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

/** Vitest configuration for the frontend: jsdom environment for component
 * tests, the React plugin for JSX/TSX transform, and tsconfig-paths so the
 * `@/*` alias defined in tsconfig.json resolves the same way it does in the
 * Next.js build. */
export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    css: true,
  },
});
