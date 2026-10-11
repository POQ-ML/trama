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
        /* Design System tokens como classes Tailwind */
        bg: "#fafafa",
        surface: "#ffffff",
        "surface-muted": "#f5f5f5",
        "surface-tabs": "#f0f0f0",
        ink: "#0a0a0a",
        "ink-hover": "#262626",
        muted: "#737373",
        border: "#d4d4d4",
        "border-soft": "#e5e5e5",
        "border-dashed-color": "#a3a3a3",

        /* aliases shadcn */
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        ring: "hsl(var(--ring))",
      },
      fontFamily: {
        sans: ["Geist", "ui-sans-serif", "system-ui", "sans-serif"],
        hand: ["Patrick Hand", "cursive"],
        mono: ["ui-monospace", "JetBrains Mono", "Menlo", "monospace"],
      },
      boxShadow: {
        /* Sombras sólidas — nunca com blur */
        "solid-sm": "2px 2px 0 #0a0a0a",
        "solid-md": "3px 3px 0 #0a0a0a",
        "solid-lg": "4px 4px 0 #0a0a0a",
        "solid-logo": "2px 2px 0 #a3a3a3",
        "solid-tab": "0 1px 2px rgba(0,0,0,.18), 0 0 0 1px #d4d4d4",
      },
      borderWidth: {
        strong: "1.5px",
      },
      borderRadius: {
        sm: "6px",
        md: "8px",
      },
    },
  },
  plugins: [],
};

export default config;
