import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: { extend: { colors: { ink: "#10223b", ink2: "#51627a", gold: "#f2a900", gain: "#0e7c5a", loss: "#c8372d", paper: "#f5f7fa", line: "#dde3ec" } } },
  plugins: [],
};
export default config;
