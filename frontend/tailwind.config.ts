import type { Config } from "tailwindcss";

/**
 * Design language: serious, analytical, enterprise. A restrained slate
 * neutral scale carries the layout; colour is reserved for meaning.
 *
 * Priority semantics are never conveyed by colour alone - every band also
 * carries a text label and an icon glyph (see components/PriorityBadge.tsx),
 * so the interface remains readable for colour-blind users and in greyscale
 * print.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Blue / white / black light-mode palette.
        // Surfaces are pure white on a faint blue-tinted ground; text is
        // near-black with a cool undertone; blue is the single accent hue.
        surface: {
          DEFAULT: "#ffffff",
          subtle: "#f5f8fc",
          muted: "#ecf1f8",
          border: "#dbe3ef",
        },
        ink: {
          DEFAULT: "#0a0f1e",
          muted: "#3d4759",
          subtle: "#5f6b82",
          inverse: "#f5f8fc",
        },
        // NHS-inspired blue family. #005EB8 is the recognisable primary,
        // #003087 the deep emphasis blue, #0072CE the interactive tint.
        // This is a design-language reference, not official NHS branding.
        brand: {
          50: "#eef5fb",
          100: "#d9eaf7",
          200: "#b9d9f0",
          500: "#0072ce",
          600: "#005eb8",
          700: "#004b9c",
          800: "#003087",
          900: "#002357",
        },
        // Priority band palette. Contrast ratios against white verified for
        // the -700 shades used for text (all >= 4.5:1).
        band: {
          // Positive green drawn from the NHS green family.
          low: "#00662f",
          lowBg: "#e9f4ed",
          lowBorder: "#a9d5ba",
          moderate: "#a16207",
          moderateBg: "#fefce8",
          moderateBorder: "#fde68a",
          high: "#c2410c",
          highBg: "#fff7ed",
          highBorder: "#fed7aa",
          critical: "#b91c1c",
          criticalBg: "#fef2f2",
          criticalBorder: "#fecaca",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.06)",
        raised:
          "0 4px 6px -1px rgb(15 23 42 / 0.07), 0 2px 4px -2px rgb(15 23 42 / 0.05)",
      },
    },
  },
  plugins: [],
};

export default config;
