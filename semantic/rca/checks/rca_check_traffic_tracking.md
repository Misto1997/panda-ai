---
kind: rca_check
id: rca_check_traffic_tracking
title: Traffic tracking guard
check: metric_shift
metric: sessions
threshold: -0.30
on_fire: warn
description: A sharp fall in sessions across all segments suggests an analytics tracking outage, not a real demand change.
---
If total sessions fall more than 30% the report is flagged as possible tracking loss.
