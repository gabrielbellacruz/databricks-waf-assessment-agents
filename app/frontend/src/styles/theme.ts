/**
 * Design tokens.
 *
 * Colors follow the Databricks brand palette. The five primary brand colors are
 * Lava 600, Navy 900, Oat Medium, Oat Light and White:
 *
 *   Lava 600   #FF3621   bright accent - use sparingly, for pops of color
 *   Navy 900   #0B2026   text and large dark surfaces
 *   Oat Medium #EEEDE9   large background surfaces
 *   Oat Light  #F9F7F4   large background surfaces
 *   White      #FFFFFF
 *
 * The extra steps below are derived from those five (tinted toward White,
 * Black, or Navy) so hovers and borders stay in the brand's warm neutral
 * family rather than drifting into cool greys.
 *
 * Surfaces are flat colors - there are deliberately no gradient tokens.
 */

export const colors = {
  /** Lava 600 - the brand accent. Fine for fills, not for text. */
  primary: '#FF3621',
  /** Lava, darkened just enough to pass AA as text on either Oat (4.87:1) */
  primaryText: '#C42919',
  /** Lava 500 - lighter Lava for subtle tints */
  primaryLight: '#FF5A49',
  /** Text color to sit on a Lava surface */
  textOnPrimary: '#FFFFFF',

  /** Navy 900 - the brand dark */
  secondary: '#0B2026',
  secondaryDark: '#08161B',
  secondaryLight: '#23363C',

  /** Navy 900 doubles as the body text color (15.7:1 on Oat Light) */
  text: '#0B2026',
  /** Navy tinted toward Oat for secondary text (5.59:1 on Oat Light) */
  textLight: '#586668',
  textInverse: '#FFFFFF',

  background: '#FFFFFF',
  /** Oat Light */
  backgroundLight: '#F9F7F4',
  /** Oat Medium */
  backgroundDark: '#EEEDE9',

  /** Oat with a little Navy mixed in, so borders stay warm */
  border: '#D3D4D2',
  borderLight: '#E3E3DF',

  success: '#197757',
  successLight: '#DCEFE7',
  warning: '#9E5600',
  warningLight: '#FBEEDC',
  error: '#C0362B',
  errorLight: '#F8E3E0',
  info: '#1F5F7A',
  infoLight: '#DEEAEF',

  /**
   * Warm neutrals for chart axes, gridlines and muted labels.
   *
   * `neutral400` is decorative only - at 3.0:1 on Oat it must not carry text.
   * `neutral500` is the lightest neutral that still passes AA as text (5.59:1),
   * so it is what the muted "answer later" status uses.
   */
  neutral400: '#A9AFAF',
  neutral500: '#586668',
  neutral800: '#0B2026',
} as const;

export const spacing = {
  xs: '0.5rem',
  sm: '1rem',
  md: '1.5rem',
  lg: '2rem',
  xl: '3rem',
  '2xl': '4rem',
} as const;

export const radius = {
  sm: '6px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  full: '9999px',
} as const;

/** Shadows are tinted with Navy rather than pure black, to match the palette */
export const shadows = {
  sm: '0 1px 3px rgba(11, 32, 38, 0.08)',
  md: '0 4px 12px rgba(11, 32, 38, 0.10)',
  lg: '0 10px 30px rgba(11, 32, 38, 0.14)',
  xl: '0 20px 50px rgba(11, 32, 38, 0.18)',
  /** Lava halo, for the hover state on primary actions */
  glow: '0 0 20px rgba(255, 54, 33, 0.30)',
} as const;

export const fonts = {
  sans: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif",
  mono: "'SF Mono', Monaco, 'Cascadia Code', 'Roboto Mono', Consolas, 'Courier New', monospace",
} as const;

export const fontSizes = {
  xs: '0.75rem',
  sm: '0.875rem',
  base: '1rem',
  lg: '1.125rem',
  xl: '1.25rem',
  '2xl': '1.5rem',
  '3xl': '1.875rem',
  '4xl': '2.25rem',
  '5xl': '3rem',
} as const;

export const transitions = {
  fast: '150ms cubic-bezier(0.4, 0, 0.2, 1)',
  base: '300ms cubic-bezier(0.4, 0, 0.2, 1)',
} as const;

export const zIndex = {
  dropdown: 1000,
  sticky: 1020,
  modal: 1050,
} as const;

export const layout = {
  headerHeight: '56px',
  containerMaxWidth: '1280px',
} as const;

/**
 * Build an `rgba()` string from one of the hex tokens above.
 *
 * Useful where a color needs real transparency rather than a flat tint - chart
 * gridlines and fills, for example, which sit over the card background.
 *
 * @param hex - Six-digit hex color, with or without the leading `#`
 * @param alpha - Opacity between 0 and 1
 */
export function withAlpha(hex: string, alpha: number): string {
  const value = hex.replace('#', '');
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Accent colour per question status, shared by badges, tags and buttons */
export const statusColors = {
  'answer-later': colors.neutral500,
  'open': colors.info,
  'in-progress': colors.warning,
  'completed': colors.success,
  'ignore': colors.textLight,
} as const;

/** Accent colour per score band, shared by the score matrix and the PDF report */
export const bandColors = {
  'met': colors.success,
  'partial': colors.warning,
  'not-met': colors.error,
} as const;

/**
 * Accent colour per backlog severity (criticality / complexity), shared by the
 * backlog panel and the PDF report. High reads as urgent (Lava), descending to
 * calm. Complexity reuses the same scale, high = most effort.
 */
export const severityColors = {
  high: colors.error,
  medium: colors.warning,
  low: colors.success,
} as const;
