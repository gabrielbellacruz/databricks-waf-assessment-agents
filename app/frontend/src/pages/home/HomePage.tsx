/**
 * Home page: introduction to the framework and entry point into an assessment.
 *
 * The about, architecture, cycle and resources sections are currently commented
 * out. Their styles and imports are commented out alongside them so the file
 * stays free of unused code; restoring a section means uncommenting both.
 */

import { css } from '@emotion/react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { colors, fontSizes, layout, radius, spacing } from '@/styles/theme';
import { PILLAR_SUMMARIES } from './pillarContent';
import { WafCycle } from './WafCycle';
// Needed by the commented-out sections below:
// import { shadows, transitions } from '@/styles/theme';
// import { DOC_RESOURCES } from './pillarContent';

export interface HomePageProps {
  onStartAssessment: () => void;
}

const containerCss = css({
  maxWidth: layout.containerMaxWidth,
  margin: '0 auto',
  padding: `${spacing.lg} ${spacing.sm}`,
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.xl,
});

const heroCss = css({
  padding: `${spacing.xl} ${spacing.lg}`,
  borderRadius: radius.xl,
  background: colors.secondary,
  color: colors.textInverse,
  textAlign: 'center',
});

const heroTitleCss = css({
  fontSize: fontSizes['4xl'],
  marginBottom: spacing.sm,
});

const heroSubtitleCss = css({
  maxWidth: '70ch',
  margin: `0 auto ${spacing.md}`,
  fontSize: fontSizes.lg,
  opacity: 0.9,
});

const sectionTitleCss = css({
  fontSize: fontSizes['2xl'],
  marginBottom: spacing.xs,
});

const sectionDescriptionCss = css({
  maxWidth: '80ch',
  color: colors.textLight,
  marginBottom: spacing.md,
});

const pillarsGridCss = css({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
  gap: spacing.sm,
});

const pillarNumberCss = css({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: '32px',
  height: '32px',
  marginBottom: spacing.xs,
  borderRadius: radius.full,
  // Darker Lava, so the white numeral stays legible
  background: colors.primary,
  color: colors.textInverse,
  fontWeight: 700,
  fontSize: fontSizes.sm,
});

const pillarNameCss = css({
  fontSize: fontSizes.lg,
  marginBottom: '6px',
});

const pillarDescCss = css({
  fontSize: fontSizes.sm,
  color: colors.textLight,
});

/* Styles for the commented-out architecture, cycle and resources sections:

const figureCss = css({
  margin: 0,
  padding: spacing.md,
  background: colors.background,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
  boxShadow: shadows.sm,
  textAlign: 'center',
});

const captionCss = css({
  marginTop: spacing.xs,
  fontSize: fontSizes.xs,
  color: colors.textLight,
});

const resourcesGridCss = css({
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
  gap: spacing.sm,
});

const resourceCardCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.sm,
  padding: spacing.sm,
  background: colors.background,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
  boxShadow: shadows.sm,
  color: colors.text,
  transition: `all ${transitions.fast}`,

  '&:hover': {
    textDecoration: 'none',
    borderColor: colors.primary,
    transform: 'translateY(-2px)',
    boxShadow: shadows.md,
  },

  h3: {
    fontSize: fontSizes.base,
  },

  p: {
    fontSize: fontSizes.sm,
    color: colors.textLight,
  },
});

*/

const ctaCss = css({
  padding: spacing.lg,
  borderRadius: radius.xl,
  // Darker Lava, so the white heading and body copy stay legible
  background: colors.primary,
  color: colors.textInverse,
  textAlign: 'center',

  h2: {
    fontSize: fontSizes['2xl'],
    marginBottom: spacing.xs,
  },

  p: {
    marginBottom: spacing.md,
    opacity: 0.92,
  },
});

export const HomePage = ({ onStartAssessment }: HomePageProps) => {
  // The commented-out image sections need this for their src attributes:
  // const baseUrl = import.meta.env.BASE_URL;

  return (
    <div css={containerCss}>
      <section css={heroCss}>
        <h2 css={heroTitleCss}>
          Welcome to the Databricks Well Architected Framework Assessment Tool
        </h2>
        <p css={heroSubtitleCss}>
          Evaluate your Databricks lakehouse architecture against industry best practices,
          assessing the seven Well Architected pillars across each layer of your data, analytics,
          and AI/ML stack.
        </p>
        <Button variant="primary" size="lg" onClick={onStartAssessment}>
          Start New Assessment
        </Button>
      </section>

      {/* <section>
        <h2 css={sectionTitleCss}>About the Well Architected Framework</h2>
        <p css={sectionDescriptionCss}>
          The Databricks Well Architected Framework (WAF) provides comprehensive guidance for
          implementing a data lakehouse on the Databricks Data Intelligence Platform. It helps
          organizations build safe, reliable, efficient, and cost-effective data and AI solutions
          through structured assessments and continuous improvement cycles.
        </p>
      </section> */}

      <section>
        <h2 css={sectionTitleCss}>The Well-Architected assessment cycle</h2>
        <p css={sectionDescriptionCss}>
          Running the framework is a continuous loop: assess your environment with the WAF agents,
          prioritize the high-risk issues, remediate them, educate your teams, then automate,
          monitor and iterate.
        </p>
        <WafCycle />
      </section>

      <section>
        <h2 css={sectionTitleCss}>The Seven Pillars of Excellence</h2>
        <p css={sectionDescriptionCss}>
          The framework is built on seven fundamental pillars that ensure comprehensive coverage of
          all critical aspects of your lakehouse architecture:
        </p>
        <div css={pillarsGridCss}>
          {PILLAR_SUMMARIES.map((pillar) => (
            <Card key={pillar.number}>
              <div css={pillarNumberCss} aria-hidden="true">
                {pillar.number}
              </div>
              <h3 css={pillarNameCss}>{pillar.name}</h3>
              <p css={pillarDescCss}>{pillar.description}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* <section>
        <h2 css={sectionTitleCss}>Lakehouse Architecture</h2>
        <p css={sectionDescriptionCss}>
          Built on open standards and unified governance, the Databricks lakehouse architecture
          combines the best of data lakes and data warehouses:
        </p>
        <figure css={figureCss}>
          <img
            src={`${baseUrl}assets/images/lakehouse-architecture-pillars.png`}
            alt="The lakehouse stack featuring Unity Catalog for unified governance, Delta Lake UniForm for open standards, and the Seven Pillars of the Well Architected Framework"
          />
          <figcaption css={captionCss}>
            The lakehouse stack featuring Unity Catalog for unified governance, Delta Lake UniForm
            for open standards, and the Seven Pillars of the Well Architected Framework
          </figcaption>
        </figure>
      </section> */}

      {/* <section>
        <h2 css={sectionTitleCss}>Platform Documentation</h2>
        <p css={sectionDescriptionCss}>
          Access comprehensive lakehouse architecture documentation specific to your cloud platform:
        </p>
        <div css={resourcesGridCss}>
          {DOC_RESOURCES.map((resource) => (
            <a
              key={resource.url}
              css={resourceCardCss}
              href={resource.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <span aria-hidden="true">☁️</span>
              <span>
                <h3>{resource.title}</h3>
                <p>{resource.description}</p>
              </span>
              <span aria-hidden="true" style={{ marginLeft: 'auto' }}>
                →
              </span>
            </a>
          ))}
        </div>
      </section> */}

      <section css={ctaCss}>
        <h2>Ready to Get Started?</h2>
        <p>
          Begin your Well Architected Framework assessment and discover insights to optimize your
          Databricks lakehouse.
        </p>
        <Button variant="secondary" size="lg" onClick={onStartAssessment}>
          Launch Assessment
        </Button>
      </section>
    </div>
  );
};
