---
kind: rca_tree
id: rca_aov_change
title: Average order value movement
root_metric: aov
movement: any
policy: rca_policy_default
preflight: [rca_check_data_freshness]
drill_dimensions: [category, customer_segment, channel, region]
hypotheses:
  - {id: h_discount, claim: "Discount depth changed", test: metric_shift, metric: discount_rate, threshold: 0.10, confirm_if: "discount_rate changes by more than 10% relative"}
---
Drills AOV by segment and checks discount depth.
