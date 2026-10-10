import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { ApiErrorState, tryLoad } from "@/components/ApiErrorState";
import { Badge } from "@/components/ui/Badge";
import { IconArrowLeft } from "@/components/ui/icons";
import { StateMessage } from "@/components/ui/StateMessage";
import { api } from "@/lib/api";
import { humanize, pluralize } from "@/lib/format";

export const metadata: Metadata = { title: "Excluded properties" };

export default async function ExcludedPage() {
  await connection();
  const { data: excluded, error } = await tryLoad(api.listExcluded);

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-muted hover:text-ink">
        <IconArrowLeft /> All apartments
      </Link>
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-ink">Excluded properties</h1>
        <p className="mt-2 text-ink-muted">
          Properties removed by hard filters — price range, unit type, location, or stale pricing. They never appear in the
          main results. A low review rating does not exclude a property: it is flagged on the property instead, and the
          browse page can filter by Google stars.
        </p>
      </div>

      {error ? (
        <ApiErrorState error={error} />
      ) : excluded.length === 0 ? (
        <StateMessage title="No excluded properties">
          <p>No property has been removed by a hard filter in the latest data.</p>
        </StateMessage>
      ) : (
        <>
          <p className="text-sm text-ink-muted">{pluralize(excluded.length, "property", "properties")} excluded</p>
          <ul className="space-y-3">
            {excluded.map((property) => (
              <li key={property.id} className="rounded-2xl border border-line bg-surface p-4 shadow-sm">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="font-semibold text-ink">{property.name}</h2>
                  <span className="text-sm text-ink-muted">{property.city ?? "City unknown"}</span>
                </div>
                <ul className="mt-3 space-y-2">
                  {property.reasons.map((reason, index) => (
                    <li key={`${reason.filter}-${index}`} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-start sm:gap-3">
                      <Badge tone="danger" className="self-start">
                        {humanize(reason.filter)}
                      </Badge>
                      <span className="text-ink-muted">{reason.explanation}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
