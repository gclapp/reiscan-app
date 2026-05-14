# REI Scan

Web application for scraping Reproductive Endocrinology & Infertility (REI) provider data from Healthgrades and Cigna.

**URL:** https://reiscan.openclapp.com

## Features

- Search REI providers by state
- Scrape data from Healthgrades (ratings, reviews, location)
- Check Cigna in-network status
- Filter by insurance network
- Export results

## Data Sources

- **Healthgrades:** Provider names, clinics, locations, scores, reviews
- **Cigna:** In-network status, covered plans

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python app.py

# Open http://localhost:5000
```

## Deployment

```bash
# Build Docker image
docker build -t reiscan .

# Run
docker run -p 5000:5000 reiscan
```

## API

```bash
POST /api/search
{
  "state": "CA",
  "sources": ["healthgrades", "cigna"],
  "network": "cigna"
}
```

## License

Private - PGNY Internal Tool
