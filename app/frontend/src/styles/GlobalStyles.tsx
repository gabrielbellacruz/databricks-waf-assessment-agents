/**
 * Global styles: reset and document-level defaults.
 * Everything else is scoped to its component via Emotion.
 */

import { Global, css } from '@emotion/react';
import { colors, fonts, fontSizes } from './theme';

const globalCss = css({
  '*, *::before, *::after': {
    boxSizing: 'border-box',
  },

  'html, body': {
    margin: 0,
    padding: 0,
  },

  body: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.base,
    lineHeight: 1.6,
    color: colors.text,
    background: colors.backgroundLight,
    WebkitFontSmoothing: 'antialiased',
    MozOsxFontSmoothing: 'grayscale',
  },

  'h1, h2, h3, h4, h5, h6': {
    margin: 0,
    lineHeight: 1.25,
    fontWeight: 600,
  },

  p: {
    margin: 0,
  },

  'button, input, textarea, select': {
    font: 'inherit',
    color: 'inherit',
  },

  button: {
    cursor: 'pointer',
  },

  'ul, ol': {
    margin: 0,
    paddingLeft: '1.25rem',
  },

  a: {
    color: colors.primaryText,
    textDecoration: 'none',
  },

  'a:hover': {
    textDecoration: 'underline',
  },

  img: {
    maxWidth: '100%',
    height: 'auto',
  },

  canvas: {
    maxWidth: '100%',
  },

  // Respect users who ask for reduced motion
  '@media (prefers-reduced-motion: reduce)': {
    '*': {
      animationDuration: '0.01ms !important',
      animationIterationCount: '1 !important',
      transitionDuration: '0.01ms !important',
    },
  },

  // Visible focus for keyboard users
  ':focus-visible': {
    outline: `2px solid ${colors.primary}`,
    outlineOffset: '2px',
  },

  // The PDF report portal is only visible while printing (see AssessmentReport)
  '@media screen': {
    '.print-report-root': {
      display: 'none',
    },
  },

  // When printing the report, hide the interactive app and print only the
  // report. Force background colours so score bands and badges survive to PDF.
  '@media print': {
    'html, body': {
      background: colors.background,
    },
    '#root': {
      display: 'none !important',
    },
    '.print-report-root': {
      display: 'block',
    },
    '.print-report-root *': {
      WebkitPrintColorAdjust: 'exact',
      printColorAdjust: 'exact',
    },
  },

  '@page': {
    margin: '16mm',
  },
});

export const GlobalStyles = () => <Global styles={globalCss} />;
