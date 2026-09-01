/**
 * Category/pillar data helpers: the selectable categories, category filtering,
 * and derived lookups over the three-level question tree.
 */

import type { Category, Pillar, Question } from '@/types/waf';

/**
 * The architecture layers an assessment is organized around. Each is a top-level
 * category holding the full set of WAF pillars. The `name` values are what an
 * assessment stores in its `categories` field.
 */
export const WAF_CATEGORIES: readonly { id: string; name: string; description: string }[] = [
  {
    id: 'ingestion',
    name: 'Ingestion',
    description: 'Bringing data into the lakehouse from source systems, streams, and files.',
  },
  {
    id: 'storage',
    name: 'Storage',
    description: 'Persisting data durably and efficiently across the lakehouse.',
  },
  {
    id: 'processing',
    name: 'Processing',
    description: 'Transforming and enriching data through batch and streaming pipelines.',
  },
  {
    id: 'orchestration',
    name: 'Orchestration',
    description: 'Scheduling, coordinating, and monitoring workflows across the platform.',
  },
  {
    id: 'analytics',
    name: 'Analytics',
    description: 'Serving data for business intelligence, reporting, and interactive queries.',
  },
  {
    id: 'ai',
    name: 'AI',
    description: 'Building and serving generative AI and LLM-based applications.',
  },
  {
    id: 'ml',
    name: 'ML',
    description: 'Developing, training, and operating machine learning models.',
  },
];

/** Category names an assessment can be scoped to, in display order */
export const AVAILABLE_CATEGORIES: readonly string[] = WAF_CATEGORIES.map(
  (category) => category.name,
);

/**
 * Filter the tree down to the selected categories.
 * Categories left without questions are dropped.
 */
export function filterCategories(categories: Category[], selectedCategories: string[]): Category[] {
  // No selection: show everything
  if (selectedCategories.length === 0) return categories;

  return categories
    .filter((category) => selectedCategories.includes(category.name))
    .filter((category) => category.pillars.some((pillar) => pillar.questions.length > 0));
}

/**
 * Unique principles of a pillar, in the order their questions appear
 */
export function getPillarPrinciples(pillar: Pillar): string[] {
  const seen = new Set<string>();
  const principles: string[] = [];

  for (const question of pillar.questions) {
    if (!question.principle || seen.has(question.principle)) continue;
    seen.add(question.principle);
    principles.push(question.principle);
  }

  return principles;
}

/**
 * Questions of a pillar belonging to one principle, keeping their pillar index
 */
export function getQuestionsForPrinciple(
  pillar: Pillar,
  principle: string,
): { question: Question; questionIndex: number }[] {
  return pillar.questions
    .map((question, questionIndex) => ({ question, questionIndex }))
    .filter((entry) => entry.question.principle === principle);
}

/**
 * Total number of questions across a set of categories
 */
export function countQuestions(categories: Category[]): number {
  return categories.reduce(
    (sum, category) =>
      sum + category.pillars.reduce((pillarSum, pillar) => pillarSum + pillar.questions.length, 0),
    0,
  );
}

/**
 * Cloud providers mentioned in a question's details text
 */
export function extractCloudProviders(details: string | null | undefined): string[] {
  if (!details) return [];

  const providers: string[] = [];
  if (details.includes('AWS')) providers.push('AWS');
  if (details.includes('Azure') || details.includes('AZURE')) providers.push('Azure');
  if (details.includes('GCP')) providers.push('GCP');
  return providers;
}
