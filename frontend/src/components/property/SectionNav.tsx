const SECTIONS = [
  { id: "pricing", label: "Price & fees" },
  { id: "units", label: "Units" },
  { id: "commute", label: "Commute" },
  { id: "scorecard", label: "Scorecard" },
  { id: "overall", label: "Overall score" },
  { id: "reviews", label: "Reviews" },
  { id: "facts", label: "Listing facts" },
  { id: "limitations", label: "Limitations" },
];

export function SectionNav() {
  return (
    <nav
      aria-label="Sections"
      className="sticky top-0 z-20 -mx-4 border-b border-line bg-bg/90 px-4 backdrop-blur sm:mx-0 sm:rounded-b-xl sm:px-0"
    >
      <ul className="flex gap-1 overflow-x-auto py-2 [scrollbar-width:none]">
        {SECTIONS.map((section) => (
          <li key={section.id} className="shrink-0">
            <a
              href={`#${section.id}`}
              className="block rounded-lg px-3 py-1.5 text-sm font-medium text-ink-muted transition hover:bg-surface hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
            >
              {section.label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
