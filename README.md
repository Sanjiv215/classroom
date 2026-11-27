# Classroom · AI Student Report Generator

A clean, modern student portal for recording academic marks, tracking attendance, and generating supportive educator remarks using Google Gemini AI.

## Features

- **Student Workspace**: Manage student profiles, sections, and notes in an intuitive educator dashboard.
- **Marks & Attendance Tracking**: Record subject marks, calculate grade averages, and track attendance metrics.
- **AI-Powered Remarks**: Draft structured, constructive report card remarks powered by Google Gemini (`gemini-3.5-flash-lite`).
- **Bulk Import**: Easily import marks and student data via CSV or Excel (`.xlsx`) files.
- **REST & External API**: Full API coverage with token authentication (`X-API-Key`) for external integrations.
- **Webhook Dispatch**: Automated `report.generated` event notifications to external webhooks.
- **Security Hardened**: Protected against timing attacks, input injection, and connection leaks with full security headers.

## Tech Stack

- **Backend**: Python 3, Flask 3.1, SQLite 3
- **AI Engine**: Google Gemini API (`gemini-3.5-flash-lite`)
- **Frontend**: Vanilla HTML5, modern CSS variables, asynchronous JavaScript
- **Data Import**: OpenPyXL, Python CSV engine

## Getting Started

### 1. Prerequisites
- Python 3.10+
- A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/Sanjiv215/classroom.git
cd classroom

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Copy the sample environment file and configure your credentials:
```bash
cp .env.example .env
```

Edit `.env`:
```env
GEMINI_API=your-gemini-api-key-here
GEMINI_MODEL=gemini-3.5-flash-lite
APP_API_KEY=your-secure-external-api-key
PORT=5050
```

### 4. Running Locally
```bash
flask --app app run --port 5050 --debug
```
Open **http://127.0.0.1:5050** in your browser.

## API Documentation

Access the interactive API documentation at:
```
GET /api/docs
```

External authenticated endpoints require `X-API-Key: <your-key>`:
- `GET /api/v1/students`: List students and academic marks
- `POST /api/v1/students`: Create or update student records
- `GET /api/v1/students/<id>/report`: Retrieve latest report card
- `POST /api/v1/students/<id>/report`: Generate a new AI report card remark

## License

MIT License. See LICENSE for details.
