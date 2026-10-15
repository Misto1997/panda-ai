---
kind: metric
id: conversion_rate
title: Conversion Rate
aliases: [CVR, session conversion]
description: Orders divided by sessions.
table: traffic
numerator: SUM(orders)
denominator: SUM(sessions)
unit: ratio
format: percent
direction: up_is_good
dimensions: [region, channel]
time_grains: [day, week, month]
---
Funnel: sessions -> checkout starts -> orders.
