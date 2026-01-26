# Python Data Ingestion System

A lightweight data ingestion system with a local SQLite database and Flask-based web UI.

## Features

- **Data Ingestion**: Import data from CSV, JSON, and Excel files
- **Local Database**: SQLite database for persistent storage (no server setup required)
- **Web UI**: Clean, responsive interface built with Flask and Bootstrap
- **Manual Entry**: Add individual records through the web interface
- **Search & Filter**: Search records by name/description, filter by source or category
- **Job Tracking**: Monitor ingestion job status and history
- **REST API**: JSON endpoints for programmatic access

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Application

```bash
python app.py
```

### 3. Open in Browser

Navigate to [http://localhost:5000](http://localhost:5000)

## Project Structure

```
├── app.py              # Flask web application
├── models.py           # SQLAlchemy database models
├── ingestion.py        # Data ingestion service
├── requirements.txt    # Python dependencies
├── templates/          # HTML templates
│   ├── base.html       # Base template with navigation
│   ├── index.html      # Dashboard
│   ├── records.html    # Data records view
│   ├── ingest.html     # File upload & manual entry
│   └── jobs.html       # Ingestion job history
├── static/
│   └── style.css       # Custom styles
└── sample_data/        # Sample data files for testing
    ├── products.csv
    └── metrics.json
```

## Data Format

### CSV Files

```csv
name,value,category,description
Product A,100,Sales,First product
Product B,200,Sales,Second product
```

### JSON Files

```json
[
  {"name": "Metric A", "value": 42, "category": "Performance"},
  {"name": "Metric B", "value": 88, "category": "Growth"}
]
```

Or with wrapper:

```json
{
  "records": [
    {"name": "Item 1", "value": 10}
  ]
}
```

### Excel Files

Excel files should have columns: `name`, `value`, `category`, `description`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/records` | GET | Get all records (supports `limit`, `offset` params) |
| `/api/stats` | GET | Get database statistics |
| `/api/jobs` | GET | Get ingestion job history |

## Database

The system uses SQLite with the database file stored as `data.db` in the project root. The database is automatically created on first run.

### Tables

- **data_records**: Stores ingested data records
- **ingestion_jobs**: Tracks ingestion job history and status

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `dev-secret-key...` | Flask secret key for sessions |

## Usage Examples

### Ingest a CSV file programmatically

```python
from models import Database
from ingestion import IngestionService

db = Database()
service = IngestionService(db)

job = service.ingest_file("data.csv", source_name="My Data")
print(f"Processed {job.records_processed} records")
```

### Add records directly

```python
records = [
    {"name": "Item 1", "value": 100, "category": "Test"},
    {"name": "Item 2", "value": 200, "category": "Test"},
]
job = service.ingest_records(records, source_name="API Import")
```

### Query records

```python
# Get all records
records = service.get_all_records(limit=100)

# Search by name/description
results = service.search_records("product")

# Filter by category
finance_records = service.get_records_by_category("Finance")
```

## License

MIT
