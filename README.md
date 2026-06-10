# Media Scrapper

A Streamlit-based scraping toolkit for extracting data from **TikTok**, **Shopee**, and **Instagram**, powered by [Apify](https://apify.com) actors.  
Runs fully inside Docker and exports results as timestamped CSV files.

---

## Getting Started

### 1. Prerequisites

- Docker installed and running
- One or more [Apify API tokens](https://console.apify.com/account/integrations) (free plan gives $5/month per account)

### 2. Build the Docker Image

```bash
sudo docker build -f DockerFile -t media_scrape .
```

### 3. Run the Container

```bash
sudo docker run -d \
  -p 8801:8801 \
  --name media_scrape \
  --shm-size="2g" \
  -v "$(pwd)/credentials:/media_scrape/credentials" \
  media_scrape
```

Or use the shortcut script:

```bash
bash rerun_app.sh
```

### 4. Open the App

```
http://localhost:8801
```

---

## Apify Token Setup

All scrapers call Apify's REST API and require at least one API token.

### Option A — Token File (recommended)

Create a plain text file with one token per line:

```
credentials/apify_token.txt
```

```
apify_api_xxxxxxxxxxxxxxxx
apify_api_yyyyyyyyyyyyyyyy
apify_api_zzzzzzzzzzzzzzzz
```

In the app, expand **Apify Token Pool**, point the path to this file, and click **Load / Reload Tokens**.

### Option B — Environment Variable

Set `APIFY_TOKEN` before starting the container:

```bash
sudo docker run -d -p 8801:8801 \
  -e APIFY_TOKEN=apify_api_xxxxxxxxxxxxxxxx \
  media_scrape
```

The app will use this token automatically and skip the file-based panel.

---

## Token Pool

Each scraper tab shows an **Apify Token Pool** expander at the top.

| Button | Action |
|---|---|
| **Load / Reload Tokens** | Reads the token file and resets to Token #1 |
| **Reset to Token #1** | Returns to the first token without reloading |
| **Check Usage** | Queries `/v2/users/me` for each token and shows monthly usage % |

**Default view** — shows only the currently active token:

![Token pool default](screenshots/first%20look%20token.png)

**After clicking Check Usage** — lists all tokens with usage percentage. Font color indicates remaining budget:

| Color | Meaning |
|---|---|
| Green | < 50% used |
| Orange | 50 – 80% used |
| Red | > 80% used |
| Gray | Could not retrieve (API error) |
| **Bold** | Currently active token |

![Token pool after check usage](screenshots/check%20usage%20token.png)

**Automatic rotation** — if a token returns HTTP 401, 402, or 429 (rate-limited / quota exceeded), the app automatically switches to the next token in the pool and retries. A warning banner appears at the top of the results section when this happens.

> Free plan limit: **$5 USD / month** per Apify account.

---

## Scrapers

### TikTok Scrapper

Actor: `GdWCkxBtKWOsKjdch`

| Scrape Type | Input |
|---|---|
| **Hashtags** | One hashtag per line (`#dance` or `dance`) |
| **Profiles** | Username or full profile URL |
| **Search Queries** | One search term per line |
| **Post URLs** | Full TikTok post URLs |

**Profile options** — Profile Sections (Videos / Liked / Reposts / Favorites) and sorting (Latest / Popular) appear when Profiles is selected.

**Search options** — Search Section, Video Sorting, and Search Date filter appear when Search Queries is selected.

**Optional Filters** (collapsed by default):

- **Date / Likes filter** — radio toggle between Date Range, Likes Range, or None.  
  TikTok rejects requests that include both date and likes filters simultaneously; selecting one mode hides the other entirely.
- **Proxy Country** — route requests through a specific country's residential proxy
- **Exclude Pinned Posts** — visible only for Profiles scrape type
- **Comments** — nested expander; all values default to 0 (disabled)

![TikTok output](screenshots/tiktok%20output.png)

---

### Shopee Scrapper

Actor: `cZrxaxPbcqHwGwSlm`

| Scrape Mode | Input |
|---|---|
| **Search by Keyword** | One keyword per line |
| **Product / Shop URL** | Full Shopee product or shop URL |
| **Shop ID** | Numeric shop ID |
| **Item ID** | Numeric item ID |
| **Category URL** | Full Shopee category URL |
| **Shop Username** | Shop slug/username |

**Selectors** — Mode, Country, and Sort By are reactive (update the input label/placeholder immediately without clicking Scrape).

**Supported countries:** Indonesia, Singapore, Malaysia, Thailand, Vietnam, Philippines, Taiwan, Brazil, Mexico, Colombia, Chile.

**Sort options:** Relevance, Top Sales, Newest, Price Low→High, Price High→Low.

**Optional Filters** (collapsed by default):

- **Min Price / Max Price** — set to 0 to disable the filter

![Shopee output](screenshots/shopee%20output.png)

---

### Instagram Scrapper

Actor: `shu8hvrXbJbY3Eb9W`

| Input Mode | Input |
|---|---|
| **Direct URLs** | One Instagram profile, post, or reel URL per line |
| **Search** | Hashtag, username, or place name |

**Results Type** — Posts, Reels, Comments, Profile Details, Mentions, or Stories. Disabled when Search mode is selected (search always returns profile details).

**Optional Filters** (collapsed by default):

- **Only posts after** — accepts `2024-01-01`, `7 days`, `3 months`, or any ISO 8601 date string

![Instagram output](screenshots/instagram%20output.png)

---

## Output

All scrapers produce:

- An interactive **data table** in the UI (media/image URL columns hidden from the main table, shown in a separate expander)
- A **JSON Response** expander showing the raw Apify payload
- A **Download CSV** button — filename includes the scrape type and a timestamp, e.g. `tiktok_profiles_20260610_143022.csv`

CSV columns vary by scrape type and are auto-generated from the actor's output. Nested JSON objects are flattened one level (e.g. `authorMeta_name`). Lists of primitives are joined with commas. Lists of objects are replaced with a count (e.g. `[5 items]`).

---

## Key Features

| Feature | Detail |
|---|---|
| **Multi-token pool** | Load any number of Apify tokens from a text file; auto-rotates on quota exhaustion |
| **Usage monitoring** | Per-token monthly usage % visible with one click |
| **No re-scraping on UI change** | Scrape results are cached in session state; changing selectors never re-triggers an API call |
| **Optional filters collapsed** | Non-essential parameters are hidden by default to reduce noise |
| **Conditional parameters** | TikTok date and likes filters are mutually exclusive — selecting one hides the other |
| **Dynamic flattener** | Works on any actor output shape; no hardcoded column mapping |
| **Timestamped CSV export** | Each download includes the scrape type and exact timestamp in the filename |
| **Docker-first** | Fully containerised; no local Python environment needed |

---

## Known Limitations

| Limitation | Detail |
|---|---|
| **Shopee variation prices are null** | Shopee's API returns null prices for products with multiple variants. Prices are only available per model via a separate endpoint not exposed by the actor. |
| **Results not persisted** | Data is held in Streamlit session state and is lost on page refresh or browser close. Export to CSV before leaving the page. |
| **Apify free plan budget** | Each token is capped at $5/month. Heavy scraping will exhaust the budget quickly; the app rotates to the next token automatically but will stop if all tokens are exhausted. |
| **No progress percentage** | Apify runs are polled every 3 seconds until completion. There is no partial result streaming. |

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Scraping backend | Apify (cloud actors) |
| Containerisation | Docker |
| Language | Python 3.11 |
