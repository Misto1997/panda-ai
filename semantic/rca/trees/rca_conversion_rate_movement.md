---
kind: rca_tree
id: rca_conversion_rate_movement
title: Conversion rate movement
root_metric: conversion_rate
policy: rca_policy_default
preflight:
- rca_check_data_freshness
- rca_check_visit_tracking
drill_dimensions:
- marketplace
- zone
marginal_dimensions:
- state
hypotheses:
- id: h_visit_denominator
  claim: Visits fell while orders stayed stable, inflating conversion
  test: divergence
  metric: visits
  other_metric: orders
  scope: top_cell
  direction: down
  threshold: 0.2
  stable_threshold: 0.05
- id: h_localized_movement
  claim: The movement is concentrated in one marketplace and zone
  test: concentration
  scope: overall
  threshold: 0.6
- id: h_orders_dropped
  claim: Orders fell overall
  test: metric_shift
  metric: orders
  scope: overall
  direction: down
  threshold: 0.05
- id: h_marketplace_mix
  claim: Visit mix shifted between marketplaces
  test: mix_shift
  metric: visits
  dimension: marketplace
  scope: overall
  threshold: 0.02
---
Separates genuine conversion changes from denominator effects.
