# MongoEngine Performance Benchmarks

Comprehensive benchmark suite for measuring and comparing sync vs async MongoDB performance with FastAPI.

## Overview

This benchmark suite helps you:
1. **Measure current sync performance** - Baseline with mongoengine (sync)
2. **Establish async ceiling** - Maximum potential with PyMongo async
3. **Compare performance** - Side-by-side analysis to justify async migration

## Project Structure

```
benchmarks/
├── fastapi_sync/          # MongoEngine sync benchmark
├── fastapi_async_native/  # PyMongo async benchmark
├── fastapi_async/         # Future: mongoengine-async (placeholder)
├── shared/                # Shared schemas and utilities
├── load_tests/            # Locust test scenarios
├── monitoring/            # Resource monitoring tools
├── scripts/               # Orchestration and analysis scripts
└── results/               # Benchmark outputs (gitignored)
```

## Quick Start

**First time? Read [SETUP.md](SETUP.md) for detailed installation instructions.**

### 1. Start MongoDB

```bash
cd fastapi_sync
docker-compose up -d mongodb
```

### 2. Run Sync Benchmark

```bash
# Terminal 1: Start sync API
cd fastapi_sync
./start.sh

# Or manually:
# cd fastapi_sync
# PYTHONPATH=.:..:..:$PYTHONPATH uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Run benchmark
cd benchmarks
pip install locust psutil numpy pandas
python scripts/run_benchmark.py --target sync --scenario realistic --users 300 --duration 5m
```

### 3. Run Async Native Benchmark

```bash
# Terminal 1: Start async API
cd fastapi_async_native
./start.sh

# Or manually:
# cd fastapi_async_native
# PYTHONPATH=.:..:..:$PYTHONPATH uvicorn app.main:app --host 0.0.0.0 --port 8001

# Terminal 2: Run benchmark
python scripts/run_benchmark.py --target async_native --scenario realistic --users 300 --duration 5m
```

### 4. Run Side-by-Side Comparison

```bash
# Make sure both APIs are running (ports 8000 and 8001)
python scripts/run_benchmark.py --compare
```

## Benchmark Scenarios

### 1. Realistic (Production-like)
- **Load**: 300 concurrent users
- **Duration**: 10-15 minutes
- **Pattern**: 70% reads, 30% writes
- **Focus**: Real-world performance

```bash
python scripts/run_benchmark.py --target sync --scenario realistic --users 300 --duration 10m
```

### 2. Concurrent Read-Heavy
- **Load**: 500 concurrent users
- **Duration**: 10 minutes
- **Pattern**: 95% reads, 5% writes
- **Focus**: Read scalability

```bash
python scripts/run_benchmark.py --target async_native --scenario realistic --users 500 --duration 10m
```

## Key Metrics

The benchmarks collect:

1. **Throughput** - Requests per second
2. **Latency** - Average, P95, P99 response times
3. **Concurrency** - Max users before degradation
4. **Resources** - CPU and memory usage

## Expected Results

| Metric | Sync (MongoEngine) | Async (PyMongo) | Improvement |
|--------|-------------------|-----------------|-------------|
| Throughput (req/s) | 100-500 | 500-5000 | 5-10x |
| Avg Latency (ms) | 50-200 | 10-50 | 2-5x |
| P95 Latency (ms) | 200-500 | 50-150 | 3-5x |
| Max Concurrent Users | 50-100 | 500-1000 | 10x |

## API Endpoints

Both sync and async benchmarks expose identical REST APIs:

### Users
- `POST /users` - Create user
- `GET /users/{id}` - Get user
- `GET /users` - List users (with pagination/filtering)
- `PUT /users/{id}` - Update user
- `PATCH /users/{id}/increment-login` - Atomic increment
- `DELETE /users/{id}` - Delete user
- `GET /users/{id}/posts` - Get user's posts

### Posts
- `POST /posts` - Create post
- `GET /posts/{id}` - Get post
- `GET /posts` - List posts
- `PUT /posts/{id}` - Update post
- `PATCH /posts/{id}/view` - Increment view count
- `DELETE /posts/{id}` - Delete post

### Batch Operations
- `POST /batch/users` - Bulk create users
- `POST /batch/posts` - Bulk create posts
- `POST /batch/analytics` - Bulk create events

### Health & Metrics
- `GET /health` - Health check
- `GET /stats` - Database statistics
- `GET /metrics` - Application metrics

## Docker Deployment

### Run Sync Benchmark with Docker

```bash
cd fastapi_sync
docker-compose up -d
```

Sync API available at: http://localhost:8000

### Run Async Benchmark with Docker

```bash
# Start MongoDB first (from fastapi_sync)
cd fastapi_sync
docker-compose up -d mongodb

# Start async API
cd ../fastapi_async_native
docker-compose up -d
```

Async API available at: http://localhost:8001

## Analyzing Results

Results are saved to `benchmarks/results/<target>_<scenario>_<timestamp>/`:

```
results/sync_realistic_20250126_143022/
├── report.html          # Locust HTML report
├── results_stats.csv    # Request statistics
├── results_failures.csv # Failure logs
├── resources.json       # CPU/memory data
├── metadata.json        # Run configuration
├── stdout.log          # Locust output
└── stderr.log          # Error output
```

### View Results

1. **HTML Report**: Open `report.html` in browser
2. **CSV Data**: Import `results_stats.csv` into Excel/pandas
3. **Resources**: Analyze `resources.json` for CPU/memory patterns

## Development

### Adding New Scenarios

Create a new file in `load_tests/scenarios/`:

```python
from locust import HttpUser, task, between

class MyScenario(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(60)
    def my_read_operation(self):
        self.client.get("/users")

    @task(40)
    def my_write_operation(self):
        self.client.post("/posts", json={...})
```

Run with:
```bash
python scripts/run_benchmark.py --target sync --scenario my_scenario --users 100 --duration 5m
```

## Troubleshooting

### MongoDB Connection Issues

```bash
# Check MongoDB is running
docker ps | grep mongodb

# Check logs
docker logs benchmark_mongodb

# Restart MongoDB
cd fastapi_sync
docker-compose restart mongodb
```

### Port Already in Use

```bash
# Check what's using the port
lsof -i :8000
lsof -i :8001

# Kill the process
kill -9 <PID>
```

### Locust Not Found

```bash
pip install locust psutil numpy pandas
```

## Next Steps

After benchmarking:

1. **Analyze Results**
   - Compare sync vs async performance
   - Identify bottlenecks
   - Determine async benefit for your use case

2. **Plan Migration**
   - Focus on high-impact operations
   - Consider gradual migration
   - Maintain API compatibility

3. **Implement mongoengine-async**
   - Use PyMongo async
   - Minimal changes to core I/O
   - Add async/await to public APIs

## Contributing

To add new benchmarks or scenarios:

1. Follow existing code structure
2. Maintain API compatibility across sync/async
3. Document expected performance improvements
4. Include realistic data patterns

## License

Same as mongoengine parent project (MIT).
