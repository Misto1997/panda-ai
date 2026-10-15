---
kind: rca_tree
id: rca_conversion_decline
title: Conversion rate movement
root_metric: conversion_rate
movement: any
policy: rca_policy_default
preflight: [rca_check_data_freshness]
drill_dimensions: [region, channel]
hypotheses:
  - {id: h_checkout_failure, claim: "Checkout or payment step is failing for a segment", test: funnel_walk, funnel: [sessions, checkout_start_rate, checkout_completion_rate], threshold: 0.15, confirm_if: "checkout_completion_rate falls >15% relative in the top segment"}
---
Drills conversion by segment using exact contribution-to-delta, then walks the funnel for the top segment.
