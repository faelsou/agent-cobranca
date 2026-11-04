import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0f1c16",
          900: "#13261c",
          800: "#1b3326",
          700: "#244233",
        },
        moss: {
          600: "#2d6a4f",
          500: "#40916c",
          100: "#d8f3dc",
        },
        paper: {
          50: "#fbf8f1",
          100: "#f4efe3",
          200: "#e7dcc6",
        },
        gold: {
          500: "#c4a35a",
        },
      },
      fontFamily: {
        display: ["Iowan Old Style", "Palatino Linotype", "Palatino", "Georgia", "serif"],
        sans: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(19, 38, 28, 0.06), 0 12px 32px -18px rgba(19, 38, 28, 0.25)",
      },
    },
  },
  plugins: [],
};

export default config;
