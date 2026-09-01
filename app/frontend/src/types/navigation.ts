/**
 * Navigation types.
 */

/** The three top-level pages */
export type PageName = 'home' | 'assessment' | 'results';

/** Which question the assessment page is showing, in the category/pillar tree */
export interface QuestionPosition {
  categoryIndex: number;
  pillarIndex: number;
  questionIndex: number;
}
