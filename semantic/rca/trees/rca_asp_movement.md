---
kind: rca_tree
id: rca_asp_movement
title: Average selling price movement
root_metric: asp
policy: rca_policy_default
preflight:
- rca_check_data_freshness
drill_dimensions:
- marketplace
- zone
marginal_dimensions:
- business_unit
- state
hypotheses:
- id: h_bu_mix_shift
  claim: Business-unit mix shifted toward lower-priced units
  test: mix_shift
  metric: net_units
  dimension: business_unit
  scope: top_cell
  threshold: 0.1
- id: h_localized_movement
  claim: The movement is concentrated in one marketplace and zone
  test: concentration
  scope: overall
  threshold: 0.5
- id: h_cancellation_bias
  claim: Cancellations skewed which units count as sold
  test: metric_shift
  metric: net_realization_rate
  scope: overall
  direction: down
  threshold: 0.05
- id: h_gross_price_drop
  claim: Order value per order fell in the affected segment
  test: metric_shift
  metric: gross_aov
  scope: top_cell
  direction: down
  threshold: 0.1
---
Checks whether ASP moved because of business-unit mix rather than price changes.
