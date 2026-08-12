# Use Python 3.11 as the base image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy dependency file
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . .

# Backend runs on port 8000
EXPOSE 8000

# Start the FastAPI server (production: no --reload; local dev overrides
# this command in compose.yaml to add --reload)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
