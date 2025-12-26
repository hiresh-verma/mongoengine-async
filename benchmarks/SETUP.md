# Benchmark Setup Guide

## Virtual Environment Options

You have two approaches for managing dependencies:

### Option 1: Single Virtual Environment (Recommended for simplicity)

Use the root mongoengine-async virtual environment for everything:

```bash
# You're already in this environment
cd /Users/hireshverma/Coding/Mine/mongoengine-async
source .venv/bin/activate  # or activate your venv

# Install all benchmark dependencies
pip install fastapi uvicorn pydantic pydantic-settings faker locust psutil numpy pandas
```

### Option 2: Separate Virtual Environments (Recommended for isolation)

Create separate environments for each benchmark:

```bash
# Sync benchmark environment
cd benchmarks/fastapi_sync
python -m venv venv_sync
source venv_sync/bin/activate
pip install -r requirements.txt
pip install -e ../../  # Install mongoengine from parent
deactivate

# Async benchmark environment
cd ../fastapi_async_native
python -m venv venv_async
source venv_async/bin/activate
pip install -r requirements.txt
deactivate
```

**For this guide, we'll use Option 1 (single environment) for simplicity.**

## Step-by-Step Setup

### 1. Install Dependencies (from root mongoengine-async directory)

```bash
cd /Users/hireshverma/Coding/Mine/mongoengine-async

# Make sure you're in your virtual environment
source .venv/bin/activate

# Install benchmark dependencies
# Note: We use PyMongo 4.0+ for native async support
pip install fastapi uvicorn[standard] pydantic pydantic-settings "pymongo>=4.0" faker locust psutil numpy pandas matplotlib
```

### 2. Start MongoDB

```bash
cd benchmarks/fastapi_sync
docker-compose up -d mongodb

# Verify it's running
docker ps | grep mongodb

# Check logs
docker logs benchmark_mongodb
```

### 3. Start Sync Benchmark API

**Option A: Use the startup script (easiest)**

```bash
cd benchmarks/fastapi_sync
./start.sh
```

**Option B: Manual command**

```bash
cd benchmarks/fastapi_sync
PYTHONPATH=.:..:..:$PYTHONPATH uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Option C: Using the run.py helper**

Create a simple run script:

```bash
cd benchmarks/fastapi_sync
python -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, '..')
sys.path.insert(0, '../..')

from app.main import app
import uvicorn

uvicorn.run(app, host='0.0.0.0', port=8000, reload=True)
"
```

### 4. Test Sync API

In a new terminal:

```bash
# Health check
curl http://localhost:8000/health

# Create a user
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "full_name": "Test User",
    "age": 30
  }'

# Get users
curl http://localhost:8000/users

# View API docs
open http://localhost:8000/docs
```

### 5. Start Async Benchmark API

In a new terminal:

```bash
cd benchmarks/fastapi_async_native
./start.sh
```

Or manually:

```bash
cd benchmarks/fastapi_async_native
PYTHONPATH=.:..:..:$PYTHONPATH uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 6. Test Async API

```bash
# Health check
curl http://localhost:8001/health

# Create a user
curl -X POST http://localhost:8001/users \
  -H "Content-Type: application/json" \
  -d '{
    "username": "asyncuser",
    "email": "async@example.com",
    "full_name": "Async User",
    "age": 25
  }'

# View API docs
open http://localhost:8001/docs
```

### 7. Run Benchmarks

With both APIs running (ports 8000 and 8001):

```bash
cd benchmarks

# Run sync benchmark
python scripts/run_benchmark.py --target sync --scenario realistic --users 100 --duration 2m

# Run async benchmark
python scripts/run_benchmark.py --target async_native --scenario realistic --users 100 --duration 2m

# Or run comparison (both)
python scripts/run_benchmark.py --compare
```

## Troubleshooting

### Issue: ModuleNotFoundError: No module named 'app'

**Solution**: Run from the correct directory and set PYTHONPATH

```bash
# From fastapi_sync directory
cd benchmarks/fastapi_sync
PYTHONPATH=.:..:..:$PYTHONPATH uvicorn app.main:app --host 0.0.0.0 --port 8000

# Or use the start.sh script
./start.sh
```

### Issue: ModuleNotFoundError: No module named 'shared'

**Solution**: Ensure PYTHONPATH includes parent directories

```bash
export PYTHONPATH=".:../..:$PYTHONPATH"
```

### Issue: Connection refused to MongoDB

**Solution**: Start MongoDB

```bash
cd benchmarks/fastapi_sync
docker-compose up -d mongodb
```

### Issue: Port already in use

**Solution**: Find and kill the process

```bash
# Find what's using port 8000
lsof -i :8000

# Kill it
kill -9 <PID>
```

## Quick Reference

### Directory Structure

```
benchmarks/
├── fastapi_sync/          # Run sync API from here
│   ├── start.sh          # Startup script
│   └── app/
│       └── main.py       # FastAPI app
├── fastapi_async_native/  # Run async API from here
│   ├── start.sh          # Startup script
│   └── app/
│       └── main.py       # FastAPI app
└── scripts/
    └── run_benchmark.py  # Run benchmarks from here
```

### Running Commands

```bash
# Start MongoDB
cd benchmarks/fastapi_sync && docker-compose up -d mongodb

# Start Sync API (Terminal 1)
cd benchmarks/fastapi_sync && ./start.sh

# Start Async API (Terminal 2)
cd benchmarks/fastapi_async_native && ./start.sh

# Run Benchmark (Terminal 3)
cd benchmarks && python scripts/run_benchmark.py --compare
```

### URLs

- Sync API: http://localhost:8000
  - Health: http://localhost:8000/health
  - Docs: http://localhost:8000/docs

- Async API: http://localhost:8001
  - Health: http://localhost:8001/health
  - Docs: http://localhost:8001/docs

## Next Steps

1. ✅ Install dependencies
2. ✅ Start MongoDB
3. ✅ Test sync API
4. ✅ Test async API
5. ✅ Run benchmarks
6. 📊 Analyze results in `benchmarks/results/`
