module.exports = {
  content: [
    "./index.html",
    "./**/*.ts",
    "./**/*.tsx",
  ],
  theme: {
    extend: {
      borderRadius: {
        xl: "1rem",
        "2xl": "1.25rem",
        "3xl": "1.5rem",
        "4xl": "1.75rem",
      },
      boxShadow: {
        soft: "0 20px 60px -40px rgba(15,23,42,.45)",
        lift: "0 30px 90px -65px rgba(2,6,23,.55)",
      },
    },
  },
  plugins: [],
};
