---
kind: dimension
id: region
title: Region
aliases:
- regions
- area
- cluster
description: Second geography level, inside a zone.
column: region
tables:
- sales
- traffic
- bu_traffic
values:
- NCR
- Northern Plains
- South West
- South East
- East Coast
- Eastern Plains
- West Coast
- Western Plains
parent: zone
children: state
---
Second geography level, inside a zone.
