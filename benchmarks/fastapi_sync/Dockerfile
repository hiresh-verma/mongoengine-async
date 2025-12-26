FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy MongoEngine from parent directory
COPY ../../mongoengine /app/mongoengine_lib
RUN cd /app/mongoengine_lib && pip install -e .

# Copy application code
COPY ./app /app/app
COPY ../shared /app/shared

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
