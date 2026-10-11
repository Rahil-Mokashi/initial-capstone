import * as Tabs from '@radix-ui/react-tabs';
import type { ReactNode } from 'react';

export interface TabSpec {
  value: string;
  label: string;
  content: ReactNode;
}

/** Keyboard-navigable tabs (arrow keys, Home/End) with the same look as the tank history tabs. */
export function TabbedPanel({
  label,
  tabs,
  defaultValue,
}: {
  label: string;
  tabs: TabSpec[];
  defaultValue?: string;
}) {
  return (
    <Tabs.Root defaultValue={defaultValue ?? tabs[0]?.value}>
      <Tabs.List aria-label={label} className="flex gap-1 border-b border-line">
        {tabs.map((t) => (
          <Tabs.Trigger
            key={t.value}
            value={t.value}
            className="min-h-[44px] border-b-2 border-transparent px-4 text-sm font-semibold text-muted data-[state=active]:border-primary data-[state=active]:text-fg"
          >
            {t.label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {tabs.map((t) => (
        <Tabs.Content key={t.value} value={t.value} className="flex flex-col gap-4 pt-4">
          {t.content}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}
