#!/bin/bash
# Quick start script for KafkaSend

set -e

echo "🚀 KafkaSend Quick Start"
echo "========================"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "✓ Docker and Docker Compose are installed"
echo ""

# Create testdata directory if it doesn't exist
mkdir -p testdata

# Create a test file if it doesn't exist
if [ ! -f testdata/test.txt ]; then
    echo "Creating test file..."
    echo "Hello from KafkaSend! This is a test file." > testdata/test.txt
    echo "✓ Test file created: testdata/test.txt"
    echo ""
fi

# Start services
echo "🐳 Starting Docker services (this may take a minute)..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy (30 seconds)..."
sleep 30

# Check service status
echo ""
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "✅ Services are running!"
echo ""
echo "📤 Sending test file..."
echo ""

# Send test file
docker-compose run --rm client send-file \
    /testdata/test.txt \
    --endpoint /api/upload \
    --method POST

echo ""
echo "🎉 Success! Your first request was sent via Kafka and processed by the portal."
echo ""
echo "📝 Next steps:"
echo "  - View portal logs:     docker-compose logs -f portal"
echo "  - View mock API logs:   docker-compose logs -f mock-api"
echo "  - Send another file:    docker-compose run --rm client send-file <path> --endpoint <endpoint>"
echo "  - Stop services:        docker-compose down"
echo ""
echo "📚 For more information, see README.md"
