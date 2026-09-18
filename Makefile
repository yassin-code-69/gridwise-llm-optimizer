.PHONY: setup run test lint docker-build docker-run benchmark clean

setup:
	uv venv --python 3.11
	uv pip install -r requirements.txt

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -v tests/

test-unit:
	pytest -v tests/unit/

test-public:
	pytest -v tests/public_cases/

docker-build:
	docker build -t gridwise-llm-optimizer:latest .

docker-run:
	docker run --rm -p 8000:8000 --env-file .env gridwise-llm-optimizer:latest

benchmark:
	python scripts/benchmark.py

judge:
	python scripts/local_judge.py --input samples/public_cases.json --mock

docker-buildx:
	docker buildx build --platform linux/amd64 -t gridwise-llm-optimizer:latest .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
