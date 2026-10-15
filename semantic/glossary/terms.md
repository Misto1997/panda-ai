---
kind: glossary
id: terms
title: Acme Retail glossary
terms:
- term: GMV
  full_form: Gross Merchandise Value
  definition: Total value of orders placed. Gross GMV is before cancellations, Net GMV after.
- term: Net GMV
  full_form: Net Gross Merchandise Value
  definition: 'Value of fulfilled orders: gross GMV minus cancellations.'
- term: Gross GMV
  full_form: Gross Merchandise Value
  definition: Value of all orders placed, including later cancelled ones.
- term: Net units
  full_form: Net units
  definition: Units that were fulfilled.
- term: Gross units
  full_form: Gross units
  definition: Units across all orders placed.
- term: ASP
  full_form: Average Selling Price
  definition: Net GMV divided by net units.
- term: AOV
  full_form: Average Order Value
  definition: Gross GMV divided by orders.
- term: CVR
  full_form: Conversion Rate
  definition: Orders divided by visits.
- term: BU
  full_form: Business Unit
  definition: A product vertical such as Electronics or Grocery.
- term: BU visits
  full_form: Business unit visits
  definition: Visits to a business unit's pages. A visit to several units counts in each, so BU visits do not sum to total visits.
- term: Visit
  full_form: Site visit
  definition: One visit to an Acme marketplace.
- term: Marketplace
  full_form: Marketplace
  definition: 'An Acme storefront: Mall, Express or Wholesale.'
- term: Zone
  full_form: Zone
  definition: 'Top geography level: North, South, East or West.'
- term: Region
  full_form: Region
  definition: Geography level below zone.
- term: State
  full_form: State
  definition: Geography level below region.
- term: City
  full_form: City
  definition: Finest geography level, available only on raw tables.
- term: Cancellation
  full_form: Order cancellation
  definition: An order that was placed but not fulfilled.
- term: Cancellation rate
  full_form: Cancellation rate
  definition: Share of gross GMV lost to cancellations.
- term: Net-to-gross
  full_form: Net-to-gross ratio
  definition: Net GMV divided by gross GMV; the complement of the cancellation rate.
- term: WoW
  full_form: Week over Week
  definition: Comparison against the preceding 7 days.
- term: MoM
  full_form: Month over Month
  definition: Comparison against the preceding month.
- term: MTD
  full_form: Month to Date
  definition: From the first of the current month to the latest day.
- term: RCA
  full_form: Root Cause Analysis
  definition: Structured investigation of why a metric moved.
- term: Rollup
  full_form: Pre-aggregated table
  definition: Daily aggregate that answers common questions without scanning raw orders.
- term: Mix shift
  full_form: Mix shift
  definition: A change in a total caused by the composition of segments changing, not the segments' own rates.
- term: Tracking loss
  full_form: Analytics tracking loss
  definition: Visits drop because instrumentation broke, while real orders stay stable; conversion then rises artificially.
- term: Materiality
  full_form: Materiality threshold
  definition: Minimum relative change worth investigating (default 3%).
- term: Baseline
  full_form: Comparison baseline
  definition: Period the current period is compared to; default is the previous period of equal length.
- term: Anchor date
  full_form: Anchor date
  definition: Latest date in the dataset; relative periods such as last 7 days resolve from it.
- term: Semantic layer
  full_form: Semantic layer
  definition: Governed definitions of metrics and dimensions the assistant must use instead of raw tables.
- term: Guardrail
  full_form: SQL guardrail
  definition: Validation that only allows read-only queries on approved tables with a row limit.
- term: Semantic cache
  full_form: Semantic cache
  definition: Cache keyed on the structured intent of a question rather than its text.
- term: Acme Mall
  full_form: Acme Mall marketplace
  definition: Flagship general-merchandise marketplace.
- term: Acme Express
  full_form: Acme Express marketplace
  definition: Fast-delivery marketplace.
- term: Acme Wholesale
  full_form: Acme Wholesale marketplace
  definition: Bulk and business buyer marketplace.
---
Terms used across Acme Retail analytics.
