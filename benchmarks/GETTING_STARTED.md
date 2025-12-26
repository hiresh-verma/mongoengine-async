# Getting Started with MongoEngine Benchmarks

## Prerequisites

- Python 3.11+
- Docker (for MongoDB)
- pip

## Step-by-Step Setup

### 1. Install Dependencies

```bash
cd benchmarks

# Install mongoengine from parent directory
cd .. && pip install -e . && cd benchmarks

# Install shared dependencies
pip install faker pydantic pydantic-settings

# Install sync benchmark dependencies
cd fastapi_sync && pip install -r requirements.txt && cd ..

# Install async benchmark dependencies
cd fastapi_async_native && pip install -r requirements.txt && cd ..

# Install load testing tools
pip install locust psutil numpy pandas matplotlib seaborn
```

### 2. Start MongoDB

```bash
cd fastapi_sync
docker-compose up -d mongodb

# Verify MongoDB is running
docker ps | grep mongodb

# Check logs
docker logs benchmark_mongodb
```

### 3. Test Sync Benchmark

```bash
# Start the sync API (in one terminal)
cd benchmarks/fastapi_sync
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal, test it
curl http://localhost:8000/health
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","full_name":"Test User","age":30}'
```

### 4. Test Async Native Benchmark

```bash
# Start the async API (in one terminal)
cd benchmarks/fastapi_async_native
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001

# In another terminal, test it
curl http://localhost:8001/health
curl -X POST http://localhost:8001/users \
  -H "Content-Type: application/json" \
  -d '{"username":"asyncuser","email":"async@example.com","full_name":"Async User","age":25}'
```

### 5. Run Your First Benchmark

```bash
# Make sure sync API is running on port 8000
cd benchmarks
python scripts/run_benchmark.py \
  --target sync \
  --scenario realistic \
  --users 100 \
  --duration 2m \
  --spawn-rate 10

# Results will be in benchmarks/results/sync_realistic_<timestamp>/
```

### 6. Compare Sync vs Async

```bash
# Make sure BOTH APIs are running (ports 8000 and 8001)
# Sync API: http://localhost:8000
# Async API: http://localhost:8001

cd benchmarks
python scripts/run_benchmark.py --compare

# This will run both benchmarks and save results for comparison
```

## Understanding the Results

After running a benchmark, you'll find results in `benchmarks/results/<target>_<scenario>_<timestamp>/`:

### Files Generated

1. **report.html** - Open in browser for visual charts
   - Request statistics
   - Response time distribution
   - Requests per second over time
   - Failure rates

2. **results_stats.csv** - Detailed statistics
   - Request counts
   - Response times (avg, min, max, median, P95, P99)
   - Requests/second
   - Failure counts

3. **resources.json** - System metrics
   - CPU usage over time
   - Memory usage over time
   - Process-level metrics

4. **metadata.json** - Run configuration
   - Parameters used
   - Timestamp
   - Resource summary

### Quick Analysis

```bash
# View the HTML report
open results/sync_realistic_<timestamp>/report.html

# Or on Linux
xdg-open results/sync_realistic_<timestamp>/report.html
```

## Common Scenarios

### Scenario 1: Quick Performance Check

Test with low load for quick feedback:

```bash
python scripts/run_benchmark.py --target sync --scenario realistic --users 50 --duration 1m
```

### Scenario 2: Realistic Production Load

Simulate production traffic:

```bash
python scripts/run_benchmark.py --target sync --scenario realistic --users 300 --duration 10m
```

### Scenario 3: Find Breaking Point

Gradually increase load to find limits:

```bash
# Start low
python scripts/run_benchmark.py --target sync --scenario realistic --users 100 --duration 5m

# Increase
python scripts/run_benchmark.py --target sync --scenario realistic --users 300 --duration 5m

# Push harder
python scripts/run_benchmark.py --target sync --scenario realistic --users 500 --duration 5m

# Compare error rates in reports
```

### Scenario 4: Async vs Sync Comparison

Direct comparison to see async benefits:

```bash
# Run sync benchmark
python scripts/run_benchmark.py --target sync --scenario realistic --users 300 --duration 5m

# Run async benchmark with SAME parameters
python scripts/run_benchmark.py --target async_native --scenario realistic --users 300 --duration 5m

# Compare the report.html files from both runs
```

## Interpreting Results

### Key Metrics to Compare

1. **Requests/Second (Throughput)**
   - Higher is better
   - Async should be 5-10x higher

2. **Average Response Time**
   - Lower is better
   - Should stay below 100ms for simple operations

3. **P95/P99 Response Time**
   - Measures tail latency
   - Should not spike too high under load

4. **Failure Rate**
   - Should be < 1% under normal load
   - If high, you've exceeded capacity

5. **CPU Usage**
   - Sync: High I/O wait (blocked on database)
   - Async: High CPU usage (efficient I/O)

### What to Look For

**Sync Performance Issues:**
- Requests/sec plateaus early
- Response time increases with concurrent users
- Low CPU usage (I/O bound)
- Connection pool exhaustion

**Async Performance Benefits:**
- Linear scaling with concurrent users
- Stable response times under load
- High CPU usage (efficiently using resources)
- Handles 5-10x more concurrent users

## Troubleshooting

### Issue: "Connection refused" errors

```bash
# Check if APIs are running
curl http://localhost:8000/health  # Sync
curl http://localhost:8001/health  # Async

# Check if ports are in use
lsof -i :8000
lsof -i :8001
```

### Issue: "ModuleNotFoundError"

```bash
# Make sure you're in the right directory and have installed deps
cd benchmarks
pip install -r fastapi_sync/requirements.txt
pip install -r fastapi_async_native/requirements.txt
pip install locust psutil numpy pandas
```

### Issue: MongoDB connection errors

```bash
# Restart MongoDB
cd fastapi_sync
docker-compose restart mongodb

# Check MongoDB logs
docker logs benchmark_mongodb

# Verify connection
mongosh mongodb://localhost:27017/mongoengine_benchmark
```

### Issue: High failure rates during benchmark

Possible causes:
1. **Too many concurrent users** - Reduce --users
2. **Database not ready** - Check MongoDB is healthy
3. **Connection pool too small** - Increase MONGODB_MAX_POOL_SIZE
4. **Slow queries** - Check database indexes

## Next Steps

1. **Run Initial Benchmarks**
   - Get baseline sync performance
   - Test async native ceiling
   - Compare results

2. **Analyze Bottlenecks**
   - Which operations benefit most from async?
   - Where is sync getting blocked?
   - What's the performance gap?

3. **Plan Migration**
   - Prioritize high-impact operations
   - Design mongoengine-async approach
   - Estimate migration effort

4. **Research Async ODMs**
   - Check what Beanie, ODMantic use
   - Evaluate PyMongo async
   - Plan minimal changes to mongoengine

## Tips

- **Start small**: Use low --users and short --duration first
- **Monitor resources**: Watch CPU/memory in resources.json
- **Compare apples to apples**: Use identical parameters for sync vs async
- **Warm up the database**: Run a quick test before the real benchmark
- **Check for errors**: Always review failures in the reports

## Getting Help

If you encounter issues:
1. Check the main README.md
2. Review the troubleshooting section above
3. Check MongoDB logs: `docker logs benchmark_mongodb`
4. Verify APIs are healthy: `curl http://localhost:8000/health`
