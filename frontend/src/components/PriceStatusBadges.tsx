import { Badge } from "./ui/Badge";
import { IconAlert } from "./ui/icons";
import type { PriceStatus } from "@/lib/types";

export function PriceStatusBadges({ status, hasPromotion, overImage = false }: { status: PriceStatus; hasPromotion: boolean; overImage?: boolean }) {
  const lift = overImage ? "shadow-sm" : "";
  return (
    <>
      {status === "conflict" && (
        <Badge tone="danger" className={lift}>
          <IconAlert /> Price conflict
        </Badge>
      )}
      {status === "stale" && (
        <Badge tone="warning" className={lift}>
          <IconAlert /> Stale price
        </Badge>
      )}
      {hasPromotion && (
        <Badge tone="accent" className={overImage ? "bg-surface shadow-sm" : ""}>
          Promotion
        </Badge>
      )}
    </>
  );
}
