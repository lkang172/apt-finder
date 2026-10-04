import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { ApiErrorState, tryLoad } from "@/components/ApiErrorState";
import { EligibilityCallout } from "@/components/EligibilityNotice";
import { CommutePanel } from "@/components/property/CommutePanel";
import { Limitations } from "@/components/property/Limitations";
import { ListingFacts } from "@/components/property/ListingFacts";
import { OverallBreakdown } from "@/components/property/OverallBreakdown";
import { ListingLinks, MonthlyCostCard, PriceAlerts, PricingDetails } from "@/components/property/Pricing";
import { PropertyHeader } from "@/components/property/PropertyHeader";
import { RatingSummaries, ReviewIntelligence } from "@/components/property/ReviewIntelligence";
import { Scorecard } from "@/components/property/Scorecard";
import { SectionNav } from "@/components/property/SectionNav";
import { UnitsList } from "@/components/property/UnitsList";
import { IconArrowLeft } from "@/components/ui/icons";
import { Section } from "@/components/ui/Section";
import { api } from "@/lib/api";
import { buildEvidenceIndex, buildThemeLabels } from "@/lib/evidence";
import { pluralize } from "@/lib/format";
import { hasNoReviews } from "@/lib/presentation";

const isPropertyId = (id: string) => /^\d+$/.test(id);

export async function generateMetadata({ params }: PageProps<"/properties/[id]">): Promise<Metadata> {
  const { id } = await params;
  if (!isPropertyId(id)) return { title: "Property not found" };
  const { data } = await tryLoad(() => api.getProperty(id));
  return { title: data ? `${data.name}, ${data.city}` : "Property" };
}

export default async function PropertyPage({ params }: PageProps<"/properties/[id]">) {
  await connection();
  const { id } = await params;
  if (!isPropertyId(id)) notFound();

  const [property, meta] = await Promise.all([tryLoad(() => api.getProperty(id)), tryLoad(api.getMeta)]);
  if (property.error?.status === 404) notFound();

  const backLink = (
    <Link href="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-ink-muted hover:text-ink">
      <IconArrowLeft /> All apartments
    </Link>
  );

  if (property.error) {
    return (
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-8 sm:px-6">
        {backLink}
        <ApiErrorState error={property.error} />
      </div>
    );
  }

  const detail = property.data;
  const officialUrl = detail.official_website?.url ?? null;
  const evidenceIndex = buildEvidenceIndex(detail);
  const themeLabels = buildThemeLabels(detail);
  const qualifyingUnits = detail.units.filter((unit) => unit.qualifies).length;

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      {backLink}
      <PropertyHeader detail={detail} />
      <EligibilityCallout notes={detail.eligibility_notes} />
      <PriceAlerts detail={detail} />

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <aside className="space-y-5 lg:sticky lg:top-4 lg:order-last lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto">
          <MonthlyCostCard cost={detail.monthly_cost} hasUnknownRequiredCosts={detail.has_unknown_required_costs} />
          <ListingLinks listings={detail.listings} official={detail.official_website} />
        </aside>

        <div className="min-w-0 space-y-12">
          <SectionNav />

          <Section id="pricing" title="Price & fees" description="Advertised base rent, lease terms, promotions, and every published fee.">
            <PricingDetails detail={detail} />
          </Section>

          <Section
            id="units"
            title="Units"
            description={`${pluralize(qualifyingUnits, "qualifying unit")} · studio/1BR, base rent within range, fresh pricing`}
          >
            <UnitsList units={detail.units} officialUrl={officialUrl} />
          </Section>

          <Section id="commute" title="Commute">
            <CommutePanel commute={detail.commute_detail} officeLabel={meta.data?.office.label ?? null} />
          </Section>

          <Section
            id="scorecard"
            title="Scorecard"
            description="Scores are 1–10 (10 is best). Open a category to see the claims, the evidence behind them, and the original sources."
          >
            <Scorecard
              assessments={detail.assessments}
              officialUrl={officialUrl}
              themeLabels={themeLabels}
              noReviews={hasNoReviews(detail.review)}
            />
          </Section>

          <Section id="overall" title="Overall score">
            <OverallBreakdown overall={detail.overall_detail} />
          </Section>

          <Section id="reviews" title="Review intelligence">
            <div className="space-y-5">
              <ReviewIntelligence detail={detail} evidenceIndex={evidenceIndex} officialUrl={officialUrl} />
              <RatingSummaries summaries={detail.rating_summaries} filter={detail.rating_filter} />
            </div>
          </Section>

          <Section id="facts" title="Listing facts" description="Amenities, parking, pets, lease terms, and utilities as published by each source.">
            <ListingFacts facts={detail.facts} officialUrl={officialUrl} />
          </Section>

          <Section id="limitations" title="What we couldn't verify" description="Data limitations and evidence-audit notes for this property.">
            <Limitations limitations={detail.limitations} audit={detail.audit} />
          </Section>
        </div>
      </div>
    </div>
  );
}
