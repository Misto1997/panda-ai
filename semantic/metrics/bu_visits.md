---
kind: metric
id: bu_visits
title: BU Visits
aliases:
- business unit visits
- vertical visits
- category visits
- BU traffic
description: Visits to a business unit's pages. One visit may count in several business units.
table: bu_traffic
expr: SUM(bu_visits)
unit: number
format: number
direction: up_is_good
dimensions:
- marketplace
- business_unit
- zone
- region
- state
time_grains:
- day
- week
- month
---
Do not sum across business units to get total visits.
