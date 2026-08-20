# Industrial Product Intelligence — Modern React Frontend

High-performance operations console for AI-powered product intelligence and industrial commerce data extraction.

## Features
- **Live Agent Extraction**: Interacts directly with the FastAPI backend (`/process-product`, `/batch`, `/products`).
- **Dynamic Presets**: Quick-load samples for Festo pneumatic actuators, Schneider Electric sensors, IFM proximity sensors, SKF bearings, and Siemens motors.
- **Rich Structured Views**: Technical specifications table, normalized attributes, key features & applications, source citations/evidence, quality rubric scoring, and visual schematic assets.
- **Export Options**: One-click JSON copy/download and PDF report generation via jsPDF.
- **Run History & Library**: Browse past resolutions stored in the database.

## Quick Start

### 1. Start the FastAPI Backend
From the repository root:
```bash
python main.py
# Runs FastAPI on http://127.0.0.1:8000
```

### 2. Start the Frontend
From `UI/frontend`:
```bash
npm run dev
# Runs Vite dev server on http://localhost:3000
```
