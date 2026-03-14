FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create directory for persistent database
RUN mkdir -p /app/data

COPY . .

EXPOSE 8501

# Run application - FIXED QUOTES BELOW
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
