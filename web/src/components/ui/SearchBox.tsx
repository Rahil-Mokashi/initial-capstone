import { Search } from 'lucide-react';
import { useId } from 'react';

/** A labelled search field (the label is visually hidden but read by screen readers). */
export function SearchBox({
  value,
  onChange,
  label,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  placeholder?: string;
}) {
  const id = useId();
  return (
    <div className="relative w-full max-w-sm">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <Search
        className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
        aria-hidden
      />
      <input
        id={id}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? label}
        className="min-h-[44px] w-full rounded-md border border-line-strong bg-surface pr-3 pl-9 text-base"
      />
    </div>
  );
}
