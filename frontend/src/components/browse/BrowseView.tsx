"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";
import { StateMessage } from "@/components/ui/StateMessage";
import {
  EMPTY_FILTERS,
  countActiveFilters,
  filterProperties,
  rentBoundsFor,
  sortProperties,
  type BrowseFilters,
  type SortDirection,
  type SortKey,
} from "@/lib/browse";
import { formatMoney, pluralize } from "@/lib/format";
import type { SourceNames } from "@/lib/presentation";
import type { Meta, PropertySummary } from "@/lib/types";
import { FilterBar, ViewToggle, type ViewMode } from "./FilterBar";
import { PropertyCard } from "./PropertyCard";
import type { MapPoint } from "./PropertyMap";

const PropertyMap = dynamic(() => import("./PropertyMap"), {
  ssr: false,
  loading: () => <div className="grid h-full place-items-center text-sm text-ink-faint">Loading map…</div>,
});

interface BrowseViewProps {
  items: PropertySummary[];
  total: number;
  cities: string[];
  office: Meta["office"] | null;
  search: Meta["search"] | null;
  sourceNames: SourceNames;
}

function mapLabel(property: PropertySummary): string {
  if (property.est_monthly_total_min !== null) return formatMoney(property.est_monthly_total_min);
  if (property.rent_min !== null) return `${formatMoney(property.rent_min)} base`;
  return "Price N/A";
}

export function BrowseView({ items, total, cities, office, search, sourceNames }: BrowseViewProps) {
  const [filters, setFilters] = useState<BrowseFilters>(EMPTY_FILTERS);
  const [sortKey, setSortKey] = useState<SortKey>("overall");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [view, setView] = useState<ViewMode>("grid");
  const [moreOpen, setMoreOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<number | null>(null);

  const visible = useMemo(
    () => sortProperties(filterProperties(items, filters), sortKey, sortDirection),
    [items, filters, sortKey, sortDirection],
  );
  const mapPoints = useMemo<MapPoint[]>(
    () =>
      visible.flatMap((p) =>
        p.lat !== null && p.lon !== null ? [{ id: p.id, name: p.name, lat: p.lat, lon: p.lon, label: mapLabel(p) }] : [],
      ),
    [visible],
  );
  const rentBounds = useMemo(() => rentBoundsFor(search, items), [search, items]);
  const activeFilterCount = countActiveFilters(filters);
  const missingCoordinates = visible.length - mapPoints.length;

  function selectFromMap(id: number) {
    setSelectedId(id);
    document.getElementById(`property-card-${id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  if (items.length === 0) {
    return (
      <StateMessage
        title="No apartments to show yet"
        action={
          <Link href="/excluded" className="text-sm font-medium text-accent hover:underline">
            See excluded properties →
          </Link>
        }
      >
        <p>
          No property has passed the hard filters (studio/1BR, base rent within range, fresh pricing, and location). Use
          “Refresh data” to collect listings, or check which properties were excluded and why.
        </p>
      </StateMessage>
    );
  }

  const grid = (
    <ul
      className={`grid grid-cols-1 gap-5 sm:grid-cols-2 ${view === "map" ? "xl:grid-cols-2" : "lg:grid-cols-3"}`}
      aria-label="Apartments"
    >
      {visible.map((property) => (
        <li key={property.id} className="flex">
          <PropertyCard
            property={property}
            highlighted={property.id === selectedId}
            sortKey={sortKey}
            sourceNames={sourceNames}
            baseRent={filters.baseRent}
            onHoverChange={setHoveredId}
          />
        </li>
      ))}
    </ul>
  );

  return (
    <div className="space-y-5">
      <FilterBar
        filters={filters}
        onFiltersChange={setFilters}
        cities={cities}
        rentBounds={rentBounds}
        sortKey={sortKey}
        sortDirection={sortDirection}
        onSortChange={(key, direction) => {
          setSortKey(key);
          setSortDirection(direction);
        }}
        moreOpen={moreOpen}
        onMoreOpenChange={setMoreOpen}
        activeFilterCount={activeFilterCount}
        onClear={() => setFilters(EMPTY_FILTERS)}
      />

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p aria-live="polite" className="text-ink-muted">
          Showing <span className="font-semibold text-ink">{visible.length}</span> of {pluralize(total, "apartment")} that
          passed the hard filters
        </p>
        <div className="flex items-center gap-4">
          <Link href="/excluded" className="font-medium text-accent hover:underline">
            Excluded properties →
          </Link>
          <ViewToggle view={view} onViewChange={setView} />
        </div>
      </div>

      {visible.length === 0 ? (
        <StateMessage
          title="No apartments match these filters"
          action={
            <button
              type="button"
              onClick={() => setFilters(EMPTY_FILTERS)}
              className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-ink hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            >
              Clear all filters
            </button>
          }
        >
          <p>
            Filters on scores, ratings, price, and commute hide properties where that value is unknown. The Google rating
            filter keeps unrated properties only while “Include unrated” is checked.
          </p>
        </StateMessage>
      ) : view === "map" ? (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,42%)]">
          <div className="isolate order-first h-[55vh] overflow-hidden rounded-2xl border border-line shadow-sm lg:sticky lg:top-4 lg:order-last lg:h-[calc(100vh-2rem)]">
            <PropertyMap
              points={mapPoints}
              office={office}
              activeId={hoveredId ?? selectedId}
              onSelect={selectFromMap}
            />
          </div>
          <div className="space-y-3">
            {missingCoordinates > 0 && (
              <p className="text-xs text-ink-faint">
                {pluralize(missingCoordinates, "property", "properties")} without known coordinates{" "}
                {missingCoordinates === 1 ? "isn't" : "aren't"} shown on the map.
              </p>
            )}
            {grid}
          </div>
        </div>
      ) : (
        grid
      )}
    </div>
  );
}
