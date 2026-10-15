---
kind: rca_tree
id: rca_net_gmv_movement
title: Net GMV movement
root_metric: net_gmv
policy: rca_policy_default
preflight:
- rca_check_data_freshness
- rca_check_visit_tracking
decomposition:
  formula: net_gmv = visits * conversion_rate * gross_aov * net_realization_rate
  components:
  - visits
  - conversion_rate
  - gross_aov
  - net_realization_rate
drill_dimensions:
- marketplace
- zone
marginal_dimensions:
- business_unit
- region
- state
hypotheses:
- id: h_cancellation_spike
  claim: Cancellations spiked in a segment, so fewer orders were fulfilled
  test: metric_shift
  metric: net_realization_rate
  scope: top_cell
  direction: down
  threshold: 0.1
- id: h_demand_drop
  claim: Fewer orders were placed overall
  test: metric_shift
  metric: orders
  scope: overall
  direction: down
  threshold: 0.05
- id: h_basket_shrink
  claim: Customers are placing smaller orders
  test: metric_shift
  metric: gross_aov
  scope: overall
  direction: down
  threshold: 0.05
- id: h_tracking_artifact
  claim: Visit tracking was lost while real orders stayed stable
  test: divergence
  metric: visits
  other_metric: orders
  scope: overall
  direction: down
  threshold: 0.1
  stable_threshold: 0.05
- id: h_localized_movement
  claim: The movement is concentrated in one marketplace and zone
  test: concentration
  scope: overall
  threshold: 0.6
---
Decomposes Net GMV into traffic, conversion, basket size and cancellation drag, drills the largest driver by segment, then tests five hypotheses.
