---
kind: rca_tree
id: rca_visits_movement
title: Visits movement
root_metric: visits
policy: rca_policy_default
preflight:
- rca_check_data_freshness
drill_dimensions:
- marketplace
- zone
marginal_dimensions:
- region
- state
- city
hypotheses:
- id: h_localized_outage
  claim: The drop is concentrated in one marketplace and zone
  test: concentration
  scope: overall
  threshold: 0.6
- id: h_tracking_loss
  claim: 'Visit tracking was lost: visits fell while orders stayed stable'
  test: divergence
  metric: visits
  other_metric: orders
  scope: top_cell
  direction: down
  threshold: 0.2
  stable_threshold: 0.05
- id: h_bu_visits_consistent
  claim: Business-unit visits fell as well, consistent with a site-wide instrumentation or outage issue
  test: metric_shift
  metric: bu_visits
  scope: top_cell
  direction: down
  threshold: 0.2
- id: h_conversion_artifact
  claim: Conversion rate rose only because the visit denominator fell
  test: metric_shift
  metric: conversion_rate
  scope: top_cell
  direction: up
  threshold: 0.2
- id: h_demand_decline
  claim: Real demand fell (orders down)
  test: metric_shift
  metric: orders
  scope: overall
  direction: down
  threshold: 0.05
---
Drills visits by marketplace and zone, then separates a genuine demand decline from tracking loss.
