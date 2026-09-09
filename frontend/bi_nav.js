/*
 * bi_nav.js -- Phase 16. Presentation routing between AI Analyst and Power BI pages.
 *
 * This module chooses WHICH BI page to open. It does not compute a figure, pick a definition,
 * or assign a trust level. Metric identifiers are inspected only as prefixes so the client
 * never hardcodes a registry row.
 */

export const BI_PAGES = [
  { key: 'executive', title: 'Executive Dashboard' },
  { key: 'financial', title: 'Financial Dashboard' },
  { key: 'operations', title: 'Operations Dashboard' },
  { key: 'risk', title: 'Risk & Data Quality Dashboard' },
  { key: 'insights', title: 'Insights / Attention Dashboard' },
];

const LABELS = {
  executive: 'View Executive Dashboard',
  financial: 'View Financial Dashboard',
  operations: 'View Operations Dashboard',
  risk: 'Open Risk & Data Quality',
  insights: 'View Insights / Attention',
};

export function biHref(key) {
  return '#/bi/' + (key || 'executive');
}

export function biNavLabel(key) {
  return LABELS[key] || LABELS.executive;
}

export function biKeyForMetricId(metricId) {
  const id = String(metricId || '');
  if (id.indexOf('M.RISK.') === 0) return 'risk';
  if (id.indexOf('M.OCC.') === 0 || id.indexOf('M.TEN.') === 0 ||
      id.indexOf('M.LIFE.') === 0 || id.indexOf('M.MAINT.') === 0 ||
      id.indexOf('M.EB.') === 0) {
    return 'operations';
  }
  if (id.indexOf('M.') === 0) return 'financial';
  return 'executive';
}

export function biKeyForAsk(result) {
  const intent = (result && result.owner_intent) || '';
  if (intent === 'briefing') return 'executive';
  if (intent === 'what_to_do' || intent === 'what_changed') return 'insights';
  if (intent === 'what_to_trust') return 'risk';
  const ids = (result && result.metric_ids) || [];
  if (ids.length) return biKeyForMetricId(ids[0]);
  return 'executive';
}
