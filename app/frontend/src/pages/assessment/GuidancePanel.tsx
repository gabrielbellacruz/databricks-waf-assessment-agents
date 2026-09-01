/**
 * Databricks guidance panel: collapsible help for the current question.
 */

import { css } from '@emotion/react';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { colors, fontSizes, radius, spacing, transitions } from '@/styles/theme';
import type {
  ChecklistCategory,
  CloudProvider,
  DatabricksGuidance,
  DecisionFramework,
} from '@/types/waf';

export interface GuidancePanelProps {
  guidance: DatabricksGuidance;
  cloudProvider: CloudProvider | null;
  /** Opens the edit modal, so a cloud provider can be chosen */
  onEditAssessment: () => void;
}

const containerCss = css({
  marginTop: spacing.md,
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.lg,
  overflow: 'hidden',
});

const toggleCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: spacing.xs,
  width: '100%',
  padding: `10px ${spacing.sm}`,
  background: colors.backgroundLight,
  border: 'none',
  fontSize: fontSizes.sm,
  fontWeight: 600,
  color: colors.text,
  transition: `background ${transitions.fast}`,

  '&:hover': {
    background: colors.backgroundDark,
  },
});

const contentCss = css({
  padding: spacing.sm,
  display: 'flex',
  flexDirection: 'column',
  gap: spacing.md,
});

const sectionTitleCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  marginBottom: spacing.xs,
  fontSize: fontSizes.sm,
  fontWeight: 600,
  color: colors.text,
});

const bodyTextCss = css({
  fontSize: fontSizes.sm,
  color: colors.textLight,
});

const infoCardCss = css({
  padding: spacing.sm,
  background: colors.infoLight,
  borderRadius: radius.md,
  fontSize: fontSizes.sm,

  ul: {
    marginTop: '6px',
  },

  li: {
    marginBottom: '2px',
  },
});

const suggestionCss = css({
  padding: spacing.sm,
  background: colors.warningLight,
  borderRadius: radius.md,
  fontSize: fontSizes.sm,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-start',
  gap: spacing.xs,
});

const decisionListCss = css({
  listStyle: 'none',
  padding: 0,
  fontSize: fontSizes.sm,
  color: colors.textLight,

  li: {
    display: 'flex',
    gap: '6px',
    marginBottom: '4px',
  },
});

const checklistCategoryCss = css({
  border: `1px solid ${colors.borderLight}`,
  borderRadius: radius.md,
  marginBottom: spacing.xs,
  overflow: 'hidden',
});

const checklistToggleCss = css({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  width: '100%',
  padding: `8px ${spacing.xs}`,
  background: colors.backgroundLight,
  border: 'none',
  fontSize: fontSizes.sm,
  fontWeight: 500,
  textAlign: 'left',
});

const checklistItemsCss = css({
  padding: `${spacing.xs} ${spacing.sm}`,
  fontSize: fontSizes.sm,
  color: colors.textLight,
});

/** Renders one decision group of the framework */
interface DecisionGroupProps {
  heading: string;
  icon: string;
  items: string[];
}

const DecisionGroup = ({ heading, icon, items }: DecisionGroupProps) => (
  <div>
    <h6 css={sectionTitleCss}>{heading}</h6>
    <ul css={decisionListCss}>
      {items.map((item) => (
        <li key={item}>
          <span aria-hidden="true">{icon}</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  </div>
);

/** Renders one collapsible checklist category */
interface ChecklistGroupProps {
  category: ChecklistCategory;
}

const ChecklistGroup = ({ category }: ChecklistGroupProps) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div css={checklistCategoryCss}>
      <button
        type="button"
        css={checklistToggleCss}
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
      >
        <span aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
        <span>{category.category}</span>
        <span css={{ marginLeft: 'auto', color: colors.textLight }}>
          ({category.questions.length})
        </span>
      </button>
      {isOpen && (
        <ul css={checklistItemsCss}>
          {category.questions.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      )}
    </div>
  );
};

/** Renders the decision framework section */
interface DecisionFrameworkSectionProps {
  framework: DecisionFramework;
  fallbackTitle: string;
  customerHeading: string;
  defaultHeading: string;
}

const DecisionFrameworkSection = ({
  framework,
  fallbackTitle,
  customerHeading,
  defaultHeading,
}: DecisionFrameworkSectionProps) => (
  <section>
    <h5 css={sectionTitleCss}>
      <span aria-hidden="true">🎯</span>
      {framework.title ?? fallbackTitle}
    </h5>
    {framework.useCustomerManaged && (
      <DecisionGroup heading={customerHeading} icon="✅" items={framework.useCustomerManaged} />
    )}
    {framework.useDefaultManaged && (
      <DecisionGroup heading={defaultHeading} icon="⚪" items={framework.useDefaultManaged} />
    )}
  </section>
);

export const GuidancePanel = ({
  guidance,
  cloudProvider,
  onEditAssessment,
}: GuidancePanelProps) => {
  const [isOpen, setIsOpen] = useState(false);

  const cloudInfo = cloudProvider ? guidance.cloudSpecific?.[cloudProvider] : undefined;
  const hasCloudSection = Boolean(guidance.cloudSpecific);

  return (
    <div css={containerCss}>
      <button
        type="button"
        css={toggleCss}
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
      >
        <span aria-hidden="true">💡</span>
        <span>Help me with this</span>
        <span aria-hidden="true" style={{ marginLeft: 'auto' }}>
          {isOpen ? '▴' : '▾'}
        </span>
      </button>

      {isOpen && (
        <div css={contentCss}>
          {guidance.context && (
            <section>
              <h5 css={sectionTitleCss}>
                <span aria-hidden="true">📌</span>
                Context
              </h5>
              <p css={bodyTextCss}>{guidance.context}</p>
            </section>
          )}

          {hasCloudSection && cloudInfo && cloudProvider && (
            <section>
              <h5 css={sectionTitleCss}>
                <span aria-hidden="true">☁️</span>
                Guidance {cloudProvider.toUpperCase()}
              </h5>
              <div css={infoCardCss}>
                <div>
                  <strong>Concept:</strong> {cloudInfo.concept}
                </div>
                {cloudInfo.keyPoints && (
                  <div>
                    <strong>Key Points:</strong>
                    <ul>
                      {cloudInfo.keyPoints.map((point) => (
                        <li key={point}>{point}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {cloudInfo.documentation && (
                  <a href={cloudInfo.documentation} target="_blank" rel="noopener noreferrer">
                    📚 Documentation →
                  </a>
                )}
              </div>
            </section>
          )}

          {hasCloudSection && !cloudProvider && (
            <div css={suggestionCss}>
              <p>
                <span aria-hidden="true">ℹ️ </span>
                Set the Cloud Provider in the Assessment to receive specific guidance for your environment
              </p>
              <Button variant="secondary" size="sm" onClick={onEditAssessment}>
                ⚙️ Edit Assessment
              </Button>
            </div>
          )}

          {guidance.decisionFramework && (
            <DecisionFrameworkSection
              framework={guidance.decisionFramework}
              fallbackTitle="Decision Framework"
              customerHeading="When to use customer-managed network"
              defaultHeading="When to use default network (Databricks-managed)"
            />
          )}

          {guidance.validationChecklist && guidance.validationChecklist.length > 0 && (
            <section>
              <h5 css={sectionTitleCss}>
                <span aria-hidden="true">✅</span>
                Validation Checklist
              </h5>
              {guidance.validationChecklist.map((category) => (
                <ChecklistGroup key={category.category} category={category} />
              ))}
            </section>
          )}

          {guidance.additionalResources && guidance.additionalResources.length > 0 && (
            <section>
              <h5 css={sectionTitleCss}>
                <span aria-hidden="true">📚</span>
                Additional Resources
              </h5>
              <ul css={bodyTextCss}>
                {guidance.additionalResources.map((resource) => (
                  <li key={resource.url}>
                    <a href={resource.url} target="_blank" rel="noopener noreferrer">
                      {resource.title} →
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
};
