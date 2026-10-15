---
kind: rca_check
id: rca_check_visit_tracking
title: Visit tracking guard
check: metric_shift
metric: visits
threshold: -0.3
description: A sharp fall in total visits suggests an analytics tracking outage, not a real demand change.
---
Fires when total visits fall more than 30%.
