# Full-run manifest: all 140 transcripts

Run `20260929T105821Z-683d36`, replayed from committed model outputs in solution/cache (claude-sonnet-5, prompt extract-v4). Regenerate: `python solution/scripts/build_artifacts.py`.

| transcripts | processed | skipped (internal-only) | failed | findings | actionable | rejected by evidence check | dismissed with reason | new tickets | grouped across calls | corroborations | enablement |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 140 | 134 | 6 | 0 | 388 | 80 | 0 | 308 | 41 | 6 | 21 | 7 |

Warnings logged during the run (code handled each one):

- call-115#f0 missing from grouping; kept alone

Nothing is filed by a run: every proposal waits for a person. The ticket columns count the proposals each call contributes to (a grouped ticket appears on every call it cites).

| call | account | status | findings | actionable | rejected | dismissed | new ticket | corroborate | enablement |
|---|---|---|---|---|---|---|---|---|---|
| call-001 | Meridian Health | extracted | 4 | 1 | 0 | 3 | new:call-001#f0 | - | - |
| call-002 | Northwind Logistics | extracted | 5 | 0 | 0 | 5 | - | - | - |
| call-003 | Atlas Financial | extracted | 3 | 1 | 0 | 2 | new:call-003#f1 | - | - |
| call-004 | Cedar Grove Schools | extracted | 2 | 1 | 0 | 1 | - | corr:call-004:PROJ-101 | - |
| call-005 | Vanta Retail | extracted | 4 | 1 | 0 | 3 | - | corr:call-005:PROJ-087 | - |
| call-006 | Harborline Media | extracted | 3 | 1 | 0 | 2 | new:call-006#f0 | - | - |
| call-007 | (internal) | skipped_internal | 0 | 0 | 0 | 0 | - | - | - |
| call-008 | Northwind Logistics | extracted | 2 | 2 | 0 | 0 | new:call-008#f1 | corr:call-008:PROJ-110 | - |
| call-009 | Lakeside Partners | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-010 | Atlas Financial | extracted | 4 | 2 | 0 | 2 | new:call-010#f1, new:call-010#f3 | - | - |
| call-011 | Brightpath Insurance | extracted | 3 | 1 | 0 | 2 | new:call-011#f2 | - | - |
| call-012 | Gable Group | extracted | 4 | 1 | 0 | 3 | new:call-006#f0 | - | - |
| call-013 | Ridgeway Manufacturing | extracted | 2 | 2 | 0 | 0 | new:call-013#f1 | - | enable:call-013:PROJ-095 |
| call-014 | Sunrise Hospitality | extracted | 5 | 1 | 0 | 4 | new:call-014#f4 | - | - |
| call-015 | Juniper Media | extracted | 2 | 1 | 0 | 1 | - | corr:call-015:PROJ-142 | - |
| call-016 | Bexley & Sons | extracted | 5 | 0 | 0 | 5 | - | - | - |
| call-017 | Halewood Biotech | extracted | 5 | 1 | 0 | 4 | new:call-017#f0 | - | - |
| call-018 | Orchard Grocery Co-op | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-019 | Pinnacle Realty | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-020 | Stallard Freight | extracted | 2 | 1 | 0 | 1 | - | corr:call-020:PROJ-110 | - |
| call-021 | Alderline Insurance | extracted | 5 | 1 | 0 | 4 | new:call-021#f0 | - | - |
| call-022 | Cavetto Restaurants | extracted | 0 | 0 | 0 | 0 | - | - | - |
| call-023 | Nordvik Shipping | extracted | 4 | 1 | 0 | 3 | new:call-023#f0 | - | - |
| call-024 | Ashwell Clinics | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-025 | (internal) | skipped_internal | 0 | 0 | 0 | 0 | - | - | - |
| call-026 | Berkfield University | extracted | 2 | 1 | 0 | 1 | - | corr:call-026:PROJ-138 | - |
| call-027 | Tandem Sports | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-028 | Quill Publishing | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-029 | Hanamura Trading | extracted | 4 | 2 | 0 | 2 | new:call-029#f0 | - | enable:call-029:PROJ-102 |
| call-030 | Vela Cosmetics | extracted | 5 | 1 | 0 | 4 | - | - | enable:call-030:PROJ-102 |
| call-031 | Grafton Utilities | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-032 | Marlowe Consulting | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-033 | Beacon Charter Schools | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-034 | Pemrose Insurance | extracted | 4 | 1 | 0 | 3 | new:call-034#f0 | - | - |
| call-035 | Glasshouse Studios | extracted | 3 | 1 | 0 | 2 | - | corr:call-035:PROJ-149 | - |
| call-036 | Ferris & Lake Accounting | extracted | 0 | 0 | 0 | 0 | - | - | - |
| call-037 | Osprey Rail | extracted | 5 | 1 | 0 | 4 | new:call-037#f0 | - | - |
| call-038 | Ironbark Mining | extracted | 1 | 0 | 0 | 1 | - | - | - |
| call-039 | Loomis Daycare Group | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-040 | Palmetto Hotels | extracted | 2 | 1 | 0 | 1 | - | corr:call-040:PROJ-160 | - |
| call-041 | Verity Accounting | extracted | 1 | 0 | 0 | 1 | - | - | - |
| call-042 | Meraki Tech | extracted | 4 | 1 | 0 | 3 | new:call-042#f0 | - | - |
| call-043 | Dunmore Textiles | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-044 | Southgate Retail | extracted | 4 | 2 | 0 | 2 | new:call-044#f0 | corr:call-044:PROJ-118 | - |
| call-045 | Bellweather PR | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-046 | Chandler Logistics | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-047 | Kirkfield College | extracted | 2 | 1 | 0 | 1 | - | corr:call-047:PROJ-101 | - |
| call-048 | Aurora Bakery Chain | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-049 | TrueNorth Bank | extracted | 3 | 1 | 0 | 2 | new:call-049#f0 | - | - |
| call-050 | Hollis & Partner | extracted | 1 | 0 | 0 | 1 | - | - | - |
| call-051 | Vantage Credit Union | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-052 | Kiwi Southern Freight | extracted | 2 | 1 | 0 | 1 | new:call-052#f0 | - | - |
| call-053 | Redgate Systems | extracted | 2 | 1 | 0 | 1 | - | corr:call-053:PROJ-087 | - |
| call-054 | Milburn Foods | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-055 | Foxglove Pharma | extracted | 5 | 1 | 0 | 4 | - | corr:call-055:PROJ-142 | - |
| call-056 | Trellis Gardens | extracted | 1 | 0 | 0 | 1 | - | - | - |
| call-057 | Pemberton Foods | extracted | 6 | 2 | 0 | 4 | new:call-021#f0, new:call-057#f3 | - | - |
| call-058 | Quarry Heights REIT | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-059 | Sterling Mutual | extracted | 3 | 1 | 0 | 2 | new:call-059#f0 | - | - |
| call-060 | Harlow Health | extracted | 5 | 1 | 0 | 4 | new:call-060#f0 | - | - |
| call-061 | Novak Studios | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-062 | (internal) | skipped_internal | 0 | 0 | 0 | 0 | - | - | - |
| call-063 | Crescent Dental Group | extracted | 4 | 1 | 0 | 3 | - | corr:call-063:PROJ-118 | - |
| call-064 | Bluewater Marina | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-065 | Gardner Aerospace | extracted | 3 | 1 | 0 | 2 | new:call-065#f0 | - | - |
| call-066 | Pillar & Oak | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-067 | Fenwick Capital | extracted | 3 | 1 | 0 | 2 | - | corr:call-067:PROJ-155 | - |
| call-068 | Sunhaven Resorts | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-069 | Corvus Media | extracted | 1 | 1 | 0 | 0 | new:call-069#f0 | - | - |
| call-070 | Brightside Retail | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-071 | Keystone Plumbing Co-op | extracted | 6 | 0 | 0 | 6 | - | - | - |
| call-072 | Copperline Energy | extracted | 4 | 2 | 0 | 2 | new:call-006#f0 | - | enable:call-072:PROJ-089 |
| call-073 | Falkner Law | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-074 | Windmark Insurance | extracted | 4 | 1 | 0 | 3 | - | corr:call-074:PROJ-120 | - |
| call-075 | Maple Crest Bank | extracted | 3 | 1 | 0 | 2 | new:call-075#f0 | - | - |
| call-076 | Jasper Winery | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-077 | Holt Manufacturing | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-078 | Larkfield Media | extracted | 2 | 1 | 0 | 1 | new:call-034#f0 | - | - |
| call-079 | Cobalt Gyms | extracted | 5 | 1 | 0 | 4 | - | - | enable:call-079:PROJ-102 |
| call-080 | Granite Peak Outfitters | extracted | 3 | 1 | 0 | 2 | new:call-080#f0 | - | - |
| call-081 | Silverline Events | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-082 | Twin Pines Farms | extracted | 2 | 1 | 0 | 1 | - | corr:call-082:PROJ-138 | - |
| call-083 | Osier Textiles | extracted | 6 | 0 | 0 | 6 | - | - | - |
| call-084 | Umber & Co | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-085 | Cardinal Couriers | extracted | 2 | 1 | 0 | 1 | new:call-085#f0 | - | - |
| call-086 | Halcyon Robotics | extracted | 3 | 1 | 0 | 2 | new:call-049#f0 | - | - |
| call-087 | Petals & Stems Florists | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-088 | Beaumont Insurance | extracted | 2 | 1 | 0 | 1 | new:call-088#f0 | - | - |
| call-089 | Riverstone Timber | extracted | 0 | 0 | 0 | 0 | - | - | - |
| call-090 | (internal) | skipped_internal | 0 | 0 | 0 | 0 | - | - | - |
| call-091 | Lumen Dance Academy | extracted | 3 | 1 | 0 | 2 | - | corr:call-091:PROJ-149 | - |
| call-092 | Fairweather Solar | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-093 | Whitcomb Partners | extracted | 2 | 1 | 0 | 1 | new:call-021#f0 | - | - |
| call-094 | Golden Hour Photography | extracted | 1 | 0 | 0 | 1 | - | - | - |
| call-095 | Northgate Security | extracted | 3 | 1 | 0 | 2 | new:call-095#f0 | - | - |
| call-096 | Idlewild Camps | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-097 | Sablewood Furniture | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-098 | Kepler Tutoring | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-099 | Drummond Steel | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-100 | Elmswood Care | extracted | 2 | 1 | 0 | 1 | new:call-100#f0 | - | - |
| call-101 | Taro Logistics | extracted | 3 | 1 | 0 | 2 | new:call-042#f0 | - | - |
| call-102 | Basil & Sage Catering | extracted | 4 | 1 | 0 | 3 | new:call-102#f3 | - | - |
| call-103 | Winslow Group | extracted | 4 | 1 | 0 | 3 | new:call-103#f0 | - | - |
| call-104 | Harmon Optics | extracted | 1 | 0 | 0 | 1 | - | - | - |
| call-105 | Delft Imports | extracted | 2 | 1 | 0 | 1 | - | corr:call-105:PROJ-101 | - |
| call-106 | (internal) | skipped_internal | 0 | 0 | 0 | 0 | - | - | - |
| call-107 | Bancroft Mills | extracted | 3 | 1 | 0 | 2 | new:call-107#f0 | - | - |
| call-108 | Coral Key Travel | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-109 | Prairie Rose Foods | extracted | 5 | 1 | 0 | 4 | - | - | enable:call-109:PROJ-089 |
| call-110 | Standish & Gray | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-111 | Beacon Point Marina | extracted | 2 | 1 | 0 | 1 | - | corr:call-111:PROJ-142 | - |
| call-112 | Onyx Apparel | extracted | 3 | 1 | 0 | 2 | new:call-034#f0 | - | - |
| call-113 | Thistle Brewing | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-114 | Galway Foods | extracted | 4 | 1 | 0 | 3 | - | - | enable:call-114:PROJ-095 |
| call-115 | Crane & Whitfield | extracted | 2 | 1 | 0 | 1 | new:call-115#f0 | - | - |
| call-116 | Overton Academy | extracted | 1 | 1 | 0 | 0 | - | corr:call-116:PROJ-131 | - |
| call-117 | Mistral Yachts | extracted | 1 | 0 | 0 | 1 | - | - | - |
| call-118 | Juniper & Finch | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-119 | Portside Medical | extracted | 3 | 1 | 0 | 2 | new:call-060#f0 | - | - |
| call-120 | Calloway Grain | extracted | 1 | 0 | 0 | 1 | - | - | - |
| call-121 | Hartley Insurance | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-122 | Vesper Finance | extracted | 2 | 1 | 0 | 1 | new:call-122#f0 | - | - |
| call-123 | Oakhaven Senior Living | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-124 | Pilgrim Coffee Roasters | extracted | 0 | 0 | 0 | 0 | - | - | - |
| call-125 | Ashcroft Partners | extracted | 4 | 1 | 0 | 3 | new:call-125#f2 | - | - |
| call-126 | Bloomfield Nurseries | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-127 | Sterlington Legal | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-128 | Kestrel Airlines | extracted | 3 | 1 | 0 | 2 | new:call-021#f0 | - | - |
| call-129 | Danfield Appliances | extracted | 3 | 0 | 0 | 3 | - | - | - |
| call-130 | Ryecroft Analytics | extracted | 4 | 1 | 0 | 3 | - | corr:call-130:PROJ-087 | - |
| call-131 | Montclair Cosmetics | extracted | 3 | 1 | 0 | 2 | new:call-131#f0 | - | - |
| call-132 | Fairbanks Consulting | extracted | 2 | 1 | 0 | 1 | new:call-132#f0 | - | - |
| call-133 | Tundra Outfitters | extracted | 2 | 0 | 0 | 2 | - | - | - |
| call-134 | Sequoia Ventures | extracted | 4 | 1 | 0 | 3 | new:call-049#f0 | - | - |
| call-135 | Bristlecone Labs | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-136 | Portman Grand Hotels | extracted | 3 | 2 | 0 | 1 | new:call-136#f0, new:call-136#f1 | - | - |
| call-137 | (internal) | skipped_internal | 0 | 0 | 0 | 0 | - | - | - |
| call-138 | Gilded Lily Events | extracted | 4 | 0 | 0 | 4 | - | - | - |
| call-139 | Andes Mining Co | extracted | 2 | 1 | 0 | 1 | new:call-139#f0 | - | - |
| call-140 | Harvest Moon Markets | extracted | 3 | 0 | 0 | 3 | - | - | - |
