#!/bin/bash
# Quick start script for mongoengine benchmarks

set -e  # Exit on error

BENCHMARKS_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BENCHMARKS_DIR"

echo "================================================"
echo "MongoEngine Benchmark Quick Start"
echo "================================================"
echo ""

# Check if MongoDB is running
echo "1. Checking MongoDB..."
if nc -z localhost 27017 2>/dev/null; then
    echo "   ✓ MongoDB is running on localhost:27017"
else
    echo "   ✗ MongoDB is not running"
    echo ""
    echo "   Starting MongoDB with Docker..."
    cd fastapi_sync
    docker-compose up -d mongodb
    echo "   Waiting for MongoDB to be ready..."
    sleep 5
    cd "$BENCHMARKS_DIR"
    echo "   ✓ MongoDB started"
fi

echo ""

# Check Python dependencies
echo "2. Checking Python dependencies..."
MISSING_DEPS=0

for pkg in fastapi uvicorn faker locust psutil; do
    if python -c "import $pkg" 2>/dev/null; then
        echo "   ✓ $pkg installed"
    else
        echo "   ✗ $pkg not installed"
        MISSING_DEPS=1
    fi
done

# Check PyMongo version (need 4.0+ for native async)
if python -c "import pymongo; assert pymongo.version_tuple >= (4, 0)" 2>/dev/null; then
    echo "   ✓ pymongo >= 4.0 (native async support)"
else
    echo "   ✗ pymongo < 4.0 or not installed"
    MISSING_DEPS=1
fi

if [ $MISSING_DEPS -eq 1 ]; then
    echo ""
    echo "   Installing missing dependencies..."
    pip install fastapi uvicorn[standard] pydantic pydantic-settings "pymongo>=4.0" faker locust psutil numpy pandas
    echo "   ✓ Dependencies installed"
fi

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Start Sync API (in terminal 1):"
echo "   cd $BENCHMARKS_DIR/fastapi_sync"
echo "   ./start.sh"
echo ""
echo "2. Start Async API (in terminal 2):"
echo "   cd $BENCHMARKS_DIR/fastapi_async_native"
echo "   ./start.sh"
echo ""
echo "3. Run benchmarks (in terminal 3):"
echo "   cd $BENCHMARKS_DIR"
echo "   python scripts/run_benchmark.py --compare"
echo ""
echo "Or test individual APIs:"
echo "   curl http://localhost:8000/health  # Sync API"
echo "   curl http://localhost:8001/health  # Async API"
echo ""
echo "View API docs:"
echo "   http://localhost:8000/docs  # Sync API"
echo "   http://localhost:8001/docs  # Async API"
echo ""
