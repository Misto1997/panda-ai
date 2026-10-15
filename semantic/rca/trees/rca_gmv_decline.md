---
kind: rca_tree
id: rca_gmv_decline
title: GMV movement
root_metric: gmv
movement: any
decomposition: {formula: "gmv = sessions * conversion_rate * aov", components: [sessions, conversion_rate, aov]}
policy: rca_policy_default
preflight: [rca_check_data_freshness, rca_check_traffic_tracking]
drill_dimensions: [region, channel]
hypotheses:
  - {id: h_checkout_failure, claim: "Checkout or payment step is failing for a segment", test: funnel_walk, funnel: [sessions, checkout_start_rate, checkout_completion_rate], threshold: 0.15, confirm_if: "checkout_completion_rate falls >15% relative in the top segment while sessions are stable"}
  - {id: h_traffic_drop, claim: "Fewer visitors", test: metric_shift, metric: sessions, threshold: 0.10, confirm_if: "sessions change by more than 10% relative"}
  - {id: h_basket_shift, claim: "Customers are buying smaller baskets", test: metric_shift, metric: aov, threshold: 0.05, confirm_if: "aov changes by more than 5% relative"}
---
Decomposes GMV with a log-ratio split into traffic, conversion and basket size, drills the largest component by segment, then tests named hypotheses.
