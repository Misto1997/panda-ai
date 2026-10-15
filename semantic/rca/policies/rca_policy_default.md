---
kind: rca_policy
id: rca_policy_default
title: Default RCA policy
rules:
  materiality: {value: 0.05, reason: "Ignore movements smaller than 5% relative."}
  top_k_drivers: {value: 3, reason: "Report at most three drivers."}
  min_segment_share: {value: 0.03, reason: "Ignore segments below 3% of the baseline total."}
  baseline: {value: previous_period, reason: "Compare against the preceding period of equal length."}
  attribution_floor: {value: 0.5, reason: "A driver explaining at least 50% of the movement is called primary."}
---
Applies to every tree unless a tree overrides a default.
