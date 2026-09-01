/**
 * Static content for the Home page.
 */

export interface PillarSummary {
  number: number;
  name: string;
  description: string;
}

export const PILLAR_SUMMARIES: readonly PillarSummary[] = [
  {
    number: 1,
    name: 'Governance',
    description:
      'Ensure data brings value and supports business strategy through proper governance, cataloging, and metadata management.',
  },
  {
    number: 2,
    name: 'Interoperability & Usability',
    description:
      'Enable seamless interaction with users and systems through open standards and intuitive interfaces.',
  },
  {
    number: 3,
    name: 'Operational Excellence',
    description:
      'Maintain production systems efficiently with robust monitoring, automation, and incident management.',
  },
  {
    number: 4,
    name: 'Security, Privacy & Compliance',
    description:
      'Protect data and systems from threats while meeting regulatory requirements and privacy standards.',
  },
  {
    number: 5,
    name: 'Reliability',
    description:
      'Recover from failures and continue functioning through redundancy, backup strategies, and disaster recovery.',
  },
  {
    number: 6,
    name: 'Performance Efficiency',
    description:
      'Optimize resource usage and adapt to changing demands with efficient data processing and query optimization.',
  },
  {
    number: 7,
    name: 'Cost Optimization',
    description:
      'Maximize business value while minimizing costs through resource right-sizing and usage optimization.',
  },
];

export interface DocResource {
  title: string;
  description: string;
  url: string;
}

export const DOC_RESOURCES: readonly DocResource[] = [
  {
    title: 'AWS Documentation',
    description: 'Lakehouse Architecture on Amazon Web Services',
    url: 'https://docs.databricks.com/en/lakehouse-architecture/index.html',
  },
  {
    title: 'Azure Documentation',
    description: 'Lakehouse Architecture on Microsoft Azure',
    url: 'https://learn.microsoft.com/en-gb/azure/databricks/lakehouse-architecture/',
  },
  {
    title: 'GCP Documentation',
    description: 'Lakehouse Architecture on Google Cloud Platform',
    url: 'https://docs.databricks.com/gcp/lakehouse-architecture/index.html',
  },
];
