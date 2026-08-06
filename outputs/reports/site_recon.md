# Site Recon - candidate property websites

Automated Step 0 check. No listings were scraped; only robots.txt,
sitemaps, one API probe and one page were fetched per site.

| Site | Property URLs | WP API | Rendering | Platform | Effort | Verdict |
|---|---:|---|---|---|---|---|
| harbor-property.com | 38042 | - | js-app | - | EASY (sitemap) | SCRAPE |
| camrealtyservice.com | 11381 | 11370 | js-app (JSON embedded) | WordPress | EASY (REST API) | SCRAPE - API available |
| pointerasia.com | 2305 | - | unknown | - | EASY (sitemap) | SCRAPE |
| aps.com.kh | 791 | 169 | js-app (JSON embedded) | WordPress | EASY (REST API) | SCRAPE - API available |
| khpropertyhub.com | 2 | - | server-rendered | - | MEDIUM (parse HTML) | SKIP - too few |
| ips-cambodia.com | - | - | unknown | - | UNKNOWN | INVESTIGATE - count unknown |
| estatecambodia.com | - | - | server-rendered | - | MEDIUM (parse HTML) | INVESTIGATE - count unknown |

## Details

### ips-cambodia.com

- reachable: True (https)
- robots.txt: none
- rendering: unknown
- note: no robots.txt (treated as allowed, per RFC 9309)
- note: no sitemap found
- note: could not fetch a page to test rendering

### aps.com.kh

- reachable: True (https)
- robots.txt: found
- sitemap: https://aps.com.kh/sitemap_index.xml
- urls in sitemap: 1178
- property urls: 791
- wordpress api: https://aps.com.kh/wp-json/wp/v2/posts?per_page=1 (169 records)
- rendering: js-app (JSON embedded)
- embedded json: JSON-LD
- sample urls:
    - https://aps.com.kh/apartment-condo-for-rent/
    - https://aps.com.kh/apartment-condo-for-sale/
    - https://aps.com.kh/properties/

### harbor-property.com

- reachable: True (https)
- robots.txt: found
- sitemap: https://www.harbor-property.com/api/sitemap/sitemapindex.xml
- urls in sitemap: 115491
- property urls: 38042
- rendering: js-app
- note: redirects to www.harbor-property.com
- sample urls:
    - https://www.harbor-property.com/en/house/detail/100001/chroy-chongva/apartment
    - https://www.harbor-property.com/en/house/detail/100014/chak-angrae-leu/condo
    - https://www.harbor-property.com/en/house/detail/100016/boeung-kak-i/condo

### camrealtyservice.com

- reachable: True (https)
- robots.txt: found
- sitemap: https://camrealtyservice.com/sitemap_index.xml
- urls in sitemap: 11989
- property urls: 11381
- wordpress api: https://camrealtyservice.com/wp-json/wp/v2/property?per_page=1 (11370 records)
- rendering: js-app (JSON embedded)
- embedded json: JSON-LD
- sample urls:
    - https://camrealtyservice.com/apartment-for-rent-in-phnom-penh/
    - https://camrealtyservice.com/apartment-for-rent-in-toul-kork-phnom-penh/
    - https://camrealtyservice.com/apartment-list/

### estatecambodia.com

- reachable: True (https)
- robots.txt: found
- rendering: server-rendered
- note: no sitemap found

### pointerasia.com

- reachable: True (https)
- robots.txt: found
- sitemap: https://pointerasia.com/sitemap.xml
- urls in sitemap: 2581
- property urls: 2305
- rendering: unknown
- note: could not fetch a page to test rendering
- sample urls:
    - https://pointerasia.com/property-for-rent/condo/phnom-penh/
    - https://pointerasia.com/property-for-rent/condo/phnom-penh/khan-boeng-keng-kang/
    - https://pointerasia.com/property-for-rent/condo/phnom-penh/khan-chamkar-mon/

### khpropertyhub.com

- reachable: True (https)
- robots.txt: found
- sitemap: https://khpropertyhub.com/sitemap.xml
- urls in sitemap: 53
- property urls: 2
- rendering: server-rendered
- sample urls:
    - https://khpropertyhub.com/discover/condos-pool-gym
    - https://khpropertyhub.com/guides/condo-buying-guide
