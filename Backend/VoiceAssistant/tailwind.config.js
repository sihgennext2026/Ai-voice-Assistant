/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: '#101828', soft: '#344054', muted: '#667085', faint: '#98A2B3' },
        line: { DEFAULT: '#E4E7EC', soft: '#F2F4F7' },
        canvas: '#F5F6F8',
        navy: { DEFAULT: '#0B3B6F', 600: '#124C8A', 50: '#EEF4FB', 100: '#DCE8F6' },
        leaf: { DEFAULT: '#0F7B5F', 50: '#E8F5F0', 100: '#CDEBE0' },
        saffron: { DEFAULT: '#C26A00', 50: '#FDF3E6' },
      },
      fontFamily: {
        sans: ['"Noto Sans"', 'Inter', 'system-ui', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)',
        lift: '0 12px 32px -12px rgba(11,59,111,0.25)',
      },
    },
  },
  plugins: [],
}
