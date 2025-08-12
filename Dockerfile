# Apify Python Actor base image (includes Python, Node, and Apify tooling)
FROM apify/actor-python:3.11

# Install Python deps first (leverages Docker layer caching)
WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Run the actor
CMD ["python", "-m", "main"]