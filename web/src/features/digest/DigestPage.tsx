import { useState } from 'react';
import { PageHeader } from '@/components/PageHeader';
import { TextField } from '@/components/ui/Field';
import { DigestView } from './DigestView';

/** The owner's daily digest: how the day went and what needs a decision. Opens on the latest day with a shift. */
export function DigestPage() {
  const [day, setDay] = useState('');
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader title="Daily digest" subtitle="How the day went, and what is waiting for you. Mark a day as reviewed once you have looked at it." />
      <div className="max-w-xs">
        <TextField type="date" label="Day (blank: the latest day with a shift)" value={day} onChange={(e) => setDay(e.target.value)} />
      </div>
      <DigestView day={day || undefined} />
    </div>
  );
}
