import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        void: "#05070d",
        abyss: "#080c16",
        panel: "#0b111e",
        edge: "#162032",
        neon: "#5eead4",
        violet2: "#a78bfa",
        amber2: "#fbbf24"
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "Inter", "sans-serif"],
        mono: ["ui-monospace", "JetBrains Mono", "Menlo", "monospace"]
      },
      boxShadow: {
        glow: "0 0 24px rgba(94, 234, 212, 0.25)",
        "glow-soft": "0 0 48px rgba(94, 234, 212, 0.12)",
        violet: "0 0 24px rgba(167, 139, 250, 0.25)"
      }
    }
  },
  plugins: []
};

export default config;
