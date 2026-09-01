/**
 * Application footer.
 */

import { css } from '@emotion/react';
import { colors, fontSizes, layout, spacing } from '@/styles/theme';

const footerCss = css({
  borderTop: `1px solid ${colors.borderLight}`,
  background: colors.background,
  marginTop: spacing.xl,
});

const innerCss = css({
  maxWidth: layout.containerMaxWidth,
  margin: '0 auto',
  padding: `${spacing.sm} ${spacing.sm}`,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: spacing.sm,
  flexWrap: 'wrap',
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

export const AppFooter = () => (
  <footer css={footerCss}>
    <div css={innerCss}>
      <p>&copy; {new Date().getFullYear()} Databricks. All rights reserved.</p>
      <p>Version {__APP_VERSION__}</p>
    </div>
  </footer>
);
