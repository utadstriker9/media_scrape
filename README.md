# Media Scrape

Media Scrape is a scraping toolkit for extracting product and media data from Shopee.  
It is designed to run fully inside Docker and provides a simple UI for scraping, viewing, and exporting results.

---

## 🚀 Getting Started

### 1. Build the Docker Image
sudo docker build -f DockerFile -t media_scrape .

### 2. Run the Docker Container
sudo docker run -d -p 8801:8801 --name media_scrape --shm-size="2g" media_scrape

### 3. Open the Application
Visit:

http://localhost:8801

---

## 🛒 Shopee Scraper Workflow

### Step 1 — Open the Shopee Scraper Page
Navigate to the Shopee scraper section from the sidebar.
![First Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/first.png)

### Step 2 — Login (First-Time Only)
You will see a login screen (QR or manual login depending on your setup).
![Second Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/second.png)
![Third Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/third.png)


### Step 3 — Input Product ID or URL
Paste any Shopee product ID or item URL to begin scraping.
![FOurth Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/fourth.png)

### Step 4 — View & Download Output
Scraped data appears in the table and can be downloaded as a CSV file.
![Output Screenshot](https://raw.githubusercontent.com/utadstriker9/media_scrape/main/screenshots/five.png)


---

## 🎯 Key Features

### Platform Support
- Shopee product scraper  
- TikTok media scraper (soon)

### Advanced Capabilities
- Simulates real mobile sessions  
- Rotates device fingerprints  
- Avoids rate limits through request pacing and browser behavior  
- Automatically refreshes tokens and session cookies  
- Supports captcha-solving integrations  
- Mimics touch events and app-like mobile interaction  

---

## 📂 Output Format
- CSV export  

---

## 🧱 Tech Stack
- Python  
- Streamlit   
- Docker  

---

## 📌 Roadmap (Nest Project)
- Instagram support  
- Shopee shop-level and review scraping  
- TikTok trending feed scraper  
- Proxy rotation management  

---
