.PHONY: help install install-dev test lint format clean docker-build docker-up docker-down docker-logs

help:
	@echo "KafkaSend - Available commands:"
	@echo "  make install        - Install package"
	@echo "  make install-dev    - Install package with dev dependencies"
	@echo "  make test          - Run tests"
	@echo "  make lint          - Run linters"
	@echo "  make format        - Format code with black"
	@echo "  make clean         - Remove build artifacts"
	@echo "  make docker-build  - Build Docker images"
	@echo "  make docker-up     - Start Docker services"
	@echo "  make docker-down   - Stop Docker services"
	@echo "  make docker-logs   - View Docker logs"

install:
	pip3 install -e .

install-dev:
	pip3 install -e ".[dev]"

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=kafkasend --cov-report=html --cov-report=term

lint:
	ruff check src/ tests/
	mypy src/

format:
	black src/ tests/
	ruff check --fix src/ tests/

clean:
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 10
	docker-compose ps

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

docker-test:
	@echo "Creating test file..."
	@echo "Test data from Makefile" > testdata/makefile-test.txt
	@echo "Sending test file..."
	docker-compose run --rm client send-file \
		/testdata/makefile-test.txt \
		--endpoint /api/upload \
		--method POST
