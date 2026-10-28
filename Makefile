.PHONY: install dev-api dev-web test scenarios build docker
install:
	cd backend && pip install -r requirements-dev.txt
	cd frontend && npm install
dev-api:
	cd backend && uvicorn app.main:app --reload --port 8000
dev-web:
	cd frontend && npm run dev
test:
	cd backend && pytest -q
scenarios:
	cd backend && python -m app.cli scenarios
build:
	cd frontend && npm run build
docker:
	docker compose up --build
