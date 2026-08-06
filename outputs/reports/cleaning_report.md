# Data Cleaning Report - PP PropertyLens

Bronze to Silver. Scope: condominiums, for sale, Phnom Penh.

## Cleaning funnel

| Stage | Records |
|---|---:|
| collected from all sources | 3,476 |
| for sale only | 3,241 |
| Phnom Penh only | 3,238 |
| has price and size | 3,000 |
| plausible values | 2,931 |
| unique properties | 2,463 |

### Exclusions

| Reason | Removed |
|---|---:|
| removed rentals | 235 |
| removed outside Phnom Penh | 3 |
| removed missing price or size | 238 |
| removed impossible price or size | 69 |
| removed duplicates | 468 |

## By source

| Source | Raw records | Kept | Share |
|---|---:|---:|---:|
| realestate.com.kh | 1,003 | 706 | 29% |
| khmer24.com | 245 | 119 | 5% |
| khpropertyhub.com | 927 | 694 | 28% |
| aps.com.kh | 137 | 108 | 4% |
| harbor-property.com | 944 | 642 | 26% |
| camrealtyservice.com | 220 | 194 | 8% |

## Districts

| District | Listings | Median price per m2 |
|---|---:|---:|
| Boeung Keng Kang | 506 | $2,190 |
| Meanchey | 345 | $1,316 |
| Chamkarmon | 288 | $1,906 |
| Toul Kork | 280 | $1,416 |
| Sen Sok | 239 | $1,450 |
| Chroy Changvar | 229 | $1,511 |
| Daun Penh | 144 | $1,557 |
| Chbar Ampov | 84 | $1,870 |
| Russey Keo | 49 | $1,271 |
| Prampi Makara | 42 | $1,394 |
| Pur Senchey | 17 | $1,080 |
| Kamboul | 2 | $999 |
| Dangkao | 1 | $1,687 |

## Cross-source duplicate overlap

Matched on district, bedrooms, size within 2 m2, and price within 3%.

| Sources | Duplicates removed |
|---|---:|
| khpropertyhub.com (internal) | 120 |
| harbor-property.com (internal) | 101 |
| khmer24.com / realestate.com.kh | 24 |
| harbor-property.com / khmer24.com | 21 |
| realestate.com.kh (internal) | 21 |
| harbor-property.com / khpropertyhub.com | 20 |
| khpropertyhub.com / realestate.com.kh | 20 |
| khmer24.com / khpropertyhub.com | 19 |
| aps.com.kh (internal) | 13 |
| harbor-property.com / realestate.com.kh | 12 |
| khmer24.com (internal) | 9 |
| aps.com.kh / khmer24.com | 4 |
| camrealtyservice.com / harbor-property.com | 4 |
| camrealtyservice.com (internal) | 3 |
| aps.com.kh / realestate.com.kh | 2 |
| camrealtyservice.com / realestate.com.kh | 1 |
| aps.com.kh / harbor-property.com | 1 |

## Completeness

| Field | Filled | Share |
|---|---:|---:|
| price_usd | 2,463 | 100% |
| size_m2 | 2,463 | 100% |
| bedrooms | 2,417 | 98% |
| bathrooms | 2,092 | 85% |
| floor | 2,065 | 84% |
| district | 2,226 | 90% |
| project_name | 357 | 14% |
| latitude | 0 | 0% |

## Known limitations

- Prices are **asking prices**, not final transaction prices.
- Coordinates are absent from most sources, so `coord_precision` is
  mostly `district`; distance features will use district or commune
  centroids.
- Some bedroom and district values were recovered from listing text
  rather than structured fields; these are flagged by
  `bedrooms_recovered` and `district_recovered`.
