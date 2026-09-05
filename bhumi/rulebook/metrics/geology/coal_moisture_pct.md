---
okf_version: "0.1"
id: coal_moisture_pct
kind: metric
version: 1
canonical_unit: "%"
value_type: decimal
metric_class: percentage
domain: geology
owner: "GM (Geology), CMPDI"
authority_sources: [CMPDI]
aggregation: none
review_tier: any
changed_on: 2026-09-06
change_reason: "Initial minimal entry — 8 real published facts exist behind this metric_key from the Marwatola I&II G2 report, the most of any metric currently published."
---

# Coal Moisture Percentage

Moisture content of coal on a proximate-analysis basis ("M%" in the
report's own column header), as reported in the Marwatola I&II
Geological Report's seam-range summary table (Min/Max per seam).

## Deliberately NOT written

`seam_thickness_gross`/`seam_thickness_net`/`coal_gcv`/`coal_grade_band`
have no Rule Book entries yet — none currently have a published Fact
Ledger row behind them (only auto_passed candidates were bulk-published
this session, and only for the three ash/moisture/fixed-carbon metrics).
Writing an entry for a metric with zero facts would be exactly the "demo
liability, not a feature" this session's kickoff prompt warned against.
