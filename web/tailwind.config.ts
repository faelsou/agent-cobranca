import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#12101f",
          900: "#12101f",
          800: "#26223d",
          700: "#5f5a78",
        },
        paper: {
          50: "#f7f6fc",
          100: "#eeeafe",
          200: "#e3def7",
        },
        brand: {
          700: "#5b3df5",
          600: "#4b2fe0",
          100: "#eeeafe",
        },
        signal: {
          400: "#c6f432",
          100: "#f1fccb",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(18, 16, 31, 0.05), 0 12px 32px -18px rgba(18, 16, 31, 0.2)",
      },
    },
  },
  plugins: [],
};

export default config;
