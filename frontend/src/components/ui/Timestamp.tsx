import { formatDate, formatDateTime } from "@/lib/format";

interface TimestampProps {
  iso: string;
  dateOnly?: boolean;
  className?: string;
}

export function Timestamp({ iso, dateOnly = false, className }: TimestampProps) {
  return (
    <time dateTime={iso} title={`${iso} (UTC)`} className={className}>
      {dateOnly ? formatDate(iso) : formatDateTime(iso)}
    </time>
  );
}
