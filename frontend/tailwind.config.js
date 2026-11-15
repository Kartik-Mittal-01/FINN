/** Colours are CSS variables (src/index.css) so dark/light switch without touching components. */
const v = (n) => `rgb(var(--${n}) / <alpha-value>)`
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: v('bg'), surface: v('surface'), raised: v('raised'), line: v('line'),
        ink: v('ink'), muted: v('muted'), faint: v('faint'),
        accent: v('accent'), up: v('up'), down: v('down'), warn: v('warn'), info: v('info'),
        crit: v('crit'), high: v('high'), med: v('med'),
      },
      fontFamily: {
        sans: ['"Inter"', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: { card: '0 1px 0 rgb(var(--line) / .6), 0 8px 24px -12px rgb(0 0 0 / .45)' },
    },
  },
  plugins: [],
}
