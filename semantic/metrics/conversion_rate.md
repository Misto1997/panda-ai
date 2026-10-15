---
kind: metric
id: conversion_rate
title: Conversion Rate
aliases:
- CVR
- visit conversion
- orders per visit
description: Orders divided by visits.
table: traffic
numerator: SUM(orders)
denominator: SUM(visits)
unit: percent
format: percent
direction: up_is_good
dimensions:
- marketplace
- zone
- region
- state
- city
time_grains:
- day
- week
- month
---
Rises artificially if visit tracking is lost.
