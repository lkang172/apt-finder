import { CONFIDENCE_LABEL, CONFIDENCE_TONE } from "@/lib/presentation";
import type { Confidence } from "@/lib/types";
import { Badge } from "./Badge";

export function ConfidenceBadge({ confidence, className }: { confidence: Confidence; className?: string }) {
  return (
    <Badge tone={CONFIDENCE_TONE[confidence]} className={className}>
      {confidence === "insufficient" ? CONFIDENCE_LABEL.insufficient : `${CONFIDENCE_LABEL[confidence]} confidence`}
    </Badge>
  );
}
