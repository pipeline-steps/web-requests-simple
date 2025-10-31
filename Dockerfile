FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY README.md .

# Set the entrypoint to run the application
ENTRYPOINT ["python", "-m", "app.main"]
