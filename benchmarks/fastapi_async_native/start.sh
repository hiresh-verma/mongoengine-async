#!/bin/bash
# Startup script for async native benchmark API

# Navigate to the async benchmark directory
cd "$(dirname "$0")"

# Check if MongoDB is running
echo "Checking MongoDB connection..."
if ! nc -z localhost 27017 2>/dev/null; then
    echo "WARNING: MongoDB doesn't appear to be running on localhost:27017"
    echo "Start it with: cd ../fastapi_sync && docker-compose up -d mongodb"
    echo ""
fi

# Set Python path to include parent directories for imports
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/..:$(pwd)/../.."

echo "Starting FastAPI Async Native Benchmark API..."
echo "API will be available at: http://localhost:8001"
echo "Health check: http://localhost:8001/health"
echo "API docs: http://localhost:8001/docs"
echo ""

# Run the application
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
