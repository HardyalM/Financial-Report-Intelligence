/** The product mark: a ledger page with a verified rule, drawn in the brand colours. */
export function BrandMark({ className = "size-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect x="1" y="1" width="30" height="30" rx="8" className="fill-brand" />
      <path d="M9 10.5h14M9 15.5h9M9 20.5h11" className="stroke-ink-inverse" strokeWidth="2" strokeLinecap="round" />
      <circle cx="22.5" cy="20.5" r="3.25" className="fill-brand-2 stroke-brand" strokeWidth="1.5" />
    </svg>
  );
}
