import { connection } from "next/server";
import { ApiErrorState, tryLoad } from "@/components/ApiErrorState";
import { BrowseView } from "@/components/browse/BrowseView";
import { RunStatus } from "@/components/browse/RunStatus";
import { api } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import { sourceNameMap } from "@/lib/presentation";

export default async function BrowsePage() {
  await connection();
  const [list, meta] = await Promise.all([tryLoad(api.listProperties), tryLoad(api.getMeta)]);
  const search = meta.data?.search;
  const office = meta.data?.office ?? null;
  const sourceNames = sourceNameMap(meta.data);

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-ink sm:text-4xl">Bay Area studios &amp; 1BRs</h1>
          <p className="mt-2 max-w-2xl text-ink-muted">
            {search ? (
              <>
                Base rent {formatMoney(search.min_rent)}–{formatMoney(search.max_rent)}
                {office && <> · commute to {office.label}</>}.{" "}
              </>
            ) : null}
            Every score links back to the evidence and original sources behind it.
          </p>
        </div>
        {list.data && <RunStatus initialRun={list.data.last_run} />}
      </div>

      {list.error ? (
        <ApiErrorState error={list.error} />
      ) : (
        <BrowseView
          items={list.data.items}
          total={list.data.total}
          cities={list.data.cities}
          office={office}
          sourceNames={sourceNames}
        />
      )}
    </div>
  );
}
