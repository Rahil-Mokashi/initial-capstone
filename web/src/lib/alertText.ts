// How an alert is worded in the always-visible strip: WHAT and WHERE (title / detail), then WHAT TO DO (action).
// Same wording rules as the Qt strip (app/ui/alert_strip.py).
export interface AlertLike {
  title: string;
  detail: string;
  action: string;
  is_summary: boolean;
}
export interface SummaryLike {
  total: number;
  notifications: AlertLike[];
}

export function sentence(n: AlertLike): string {
  const parts = [`${n.title.replace(/\.+$/, '')}.`];
  if (n.detail) parts.push(n.detail);
  if (n.action) parts.push(n.action);
  return parts.join(' ');
}

export function collapsedSummaryText(summary: SummaryLike | null | undefined): string {
  if (!summary) return 'Checking for alerts…';
  if (summary.total === 0) return 'All clear — nothing needs attention right now.';
  const shown = summary.notifications.filter((n) => !n.is_summary);
  if (shown.length === 1) return sentence(shown[0]!);
  const worst = shown[0] ?? summary.notifications[0]!;
  const plural = summary.total === 1 ? 'alert' : 'alerts';
  return `${summary.total} ${plural} need attention — most urgent: ${worst.title}.`;
}

export const SEVERITY_LABEL: Record<string, string> = {
  critical: 'NEEDS ATTENTION',
  warning: 'WORTH A LOOK',
  info: 'FOR INFORMATION',
};
