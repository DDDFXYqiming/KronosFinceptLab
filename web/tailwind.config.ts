import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#0052FF",
          light: "#4D7CFF",
          dark: "#003ECF",
        },
        surface: {
          DEFAULT: "#0A0E1A",
          raised: "#111827",
          overlay: "#1F2937",
        },
        accent: {
          green: "#10B981",
          red: "#EF4444",
          amber: "#F59E0B",
        },
      },
      fontFamily: {
        display: ["Calistoga", "serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      backgroundImage: {
        "gradient-primary": "linear-gradient(135deg, #0052FF 0%, #4D7CFF 100%)",
      },
    },
  },
  plugins: [],
};

export default config;
