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

# Backend runs on port 8000 locally; hosts like Railway inject PORT at
# runtime and route traffic there, so the bind must follow it or every
# request hits a closed port (502) even though the process is healthy.
EXPOSE 8000

# Shell form so $PORT is expanded at container start, not build time
# (production: no --reload; local dev overrides this command in
# compose.yaml to add --reload).
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
