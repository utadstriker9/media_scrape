# Media Scrape

Media Scrape is a scraping toolkit for extracting product and media data from Shopee, TikTok, and Instagram powered by Apify.  
It is designed to run fully inside Docker and provides a simple Streamlit UI for scraping, viewing, and exporting results.

---

## Getting Started

### 1. Build the Docker Image
```bash
sudo docker build -f DockerFile -t media_scrape .
```

### 2. Run the Docker Container
```bash
sudo docker run -d \
  -p 8801:8801 \
  --name media_scrape \
  --shm-size="2g" \
  -v "$(pwd)/modules/output:/media_scrape/modules/output" \
  media_scrape
```
> The `-v` volume mount keeps your cookie files alive across container rebuilds.  
> Or just run `bash rerun_app.sh` which does all of the above automatically.

### 3. Open the Application
```
http://localhost:8801
```

---

## Scraper Workflow


---

## Key Features

| Feature | Status |
|---|---|
| Shopee product scraper | ✅ Active |
| JSON-first data extraction | ✅ Active |
| Session health check | ✅ Active |
| TikTok media scraper | ✅ Active |
| Instagram media scraper | ✅ Active |

---

## 🛡️ Anti-Detection Strategy

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Containerisation | Docker |
| Language | Python 3.11 |

---