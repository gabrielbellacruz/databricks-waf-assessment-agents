/**
 * WAF data loading.
 * Fetches the question set served at `/data/` (canonical file is repo-root
 * `/data/waf-data.json`, copied into `public/data` at build). Three-level tree:
 * architecture-step category -> WAF pillar -> question.
 */

import type { Category } from '@/types/waf';

const BASE_URL = import.meta.env.BASE_URL;

export interface WafData {
  categories: Category[];
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to load ${url}: HTTP ${response.status}`);
  return await response.json();
}

/**
 * Load the categories and their pillars.
 */
export async function loadWafData(): Promise<WafData> {
  const categories = await fetchJson<Category[]>(`${BASE_URL}data/waf-data.json`);
  return { categories };
}
