/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // MSHFI Dark Theme
        bg: "#0b0f14",
        surface: "#11161d",
        surface2: "#182029",
        border: "#232b37",
        border2: "#2c3645",
        accent: "#2dd4bf",
        accent2: "#14b8a6",
        "accent-glow": "rgba(45, 212, 191, 0.12)",
        blue: "#4f8ef7",
        text: "#e9edf1",
        text2: "#8b94a3",
        text3: "#555f70",
        success: "#34d399",
        warning: "#f5a623",
        danger: "#f0625f",
        purple: "#a78bfa",
      },
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        mono: ["DM Mono", "monospace"],
      },
      borderRadius: {
        DEFAULT: "10px",
        lg: "16px",
      },
      fontSize: {
        xs: "10px",
        sm: "12px",
        base: "13px",
        lg: "14px",
        xl: "14.5px",
        "2xl": "21px",
      },
      animation: {
        fadeIn: "fadeIn 0.2s ease",
        slideIn: "slideIn 0.2s ease",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        slideIn: {
          from: { opacity: "0", transform: "translateX(20px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
      },
    },
  },
  plugins: [],
}
