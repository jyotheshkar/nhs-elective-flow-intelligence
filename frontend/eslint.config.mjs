import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

/**
 * ESLint flat config.
 *
 * eslint-config-next v16 exports flat configs directly, so no FlatCompat shim
 * is needed (and using one breaks on this version).
 */
const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts", "out/**"],
  },
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    rules: {
      // Analytical payloads are typed at the API boundary; an `any` inside a
      // component would silently defeat that, so it stays an error.
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
];

export default config;
