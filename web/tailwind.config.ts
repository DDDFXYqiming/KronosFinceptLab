import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Accent - Electric Blue gradient (both themes)
        accent: {
          DEFAULT: "#0052FF",
          secondary: "#4D7CFF",
          foreground: "#FFFFFF",
        },

        // Light theme (default)
        background: "#FAFAFA",
        foreground: "#0F172A",
        muted: "#F1F5F9",
        "muted-foreground": "#64748B",
        border: "#E2E8F0",
        card: "#FFFFFF",
        ring: "#0052FF",

        // Surface colors (dark theme)
        surface: {
          DEFAULT: "#0A0E1A",
          raised: "#111827",
          overlay: "#1F2937",
        },

        // Status colors
        success: "#10B981",
        error: "#EF4444",
        warning: "#F59E0B",
      },
      fontFamily: {
        display: ["Calistoga", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backgroundImage: {
        "gradient-primary": "linear-gradient(135deg, #0052FF 0%, #4D7CFF 100%)",
        "gradient-accent": "linear-gradient(to right, #0052FF, #4D7CFF)",
      },
      boxShadow: {
        "accent-sm": "0 4px 14px rgba(0, 82, 255, 0.25)",
        "accent-lg": "0 8px 24px rgba(0, 82, 255, 0.35)",
      },
      borderRadius: {
        xl: "12px",
        "2xl": "16px",
      },
      keyframes: {
        "pulse-dot": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.7", transform: "scale(1.3)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        "rotate-slow": {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        "fade-in-up": {
          from: { opacity: "0", transform: "translateY(28px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-dot": "pulse-dot 2s infinite",
        float: "float 5s ease-in-out infinite",
        "rotate-slow": "rotate-slow 60s linear infinite",
        "fade-in-up": "fade-in-up 0.7s ease-out forwards",
      },
    },
  },
  plugins: [],
};

export default config;
