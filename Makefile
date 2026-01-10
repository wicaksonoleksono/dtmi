include .env
export

.PHONY: help build up down logs shell restart clean db-up db-down db-logs db-shell all-up all-down

help:
	@echo "Optima Flask App - Docker Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Flask App:"
	@echo "  build      - Build the Flask app image"
	@echo "  up         - Start Flask app container"
	@echo "  down       - Stop Flask app container"
	@echo "  logs       - View Flask app logs"
	@echo "  shell      - Open shell in Flask container"
	@echo "  restart    - Restart Flask app"
	@echo "  clean      - Remove Flask container and image"
	@echo ""
	@echo "Database (ChromaDB):"
	@echo "  db-up      - Start ChromaDB container"
	@echo "  db-down    - Stop ChromaDB container"
	@echo "  db-logs    - View ChromaDB logs"
	@echo "  db-shell   - Open shell in ChromaDB container"
	@echo ""
	@echo "Full Stack:"
	@echo "  all-up     - Start ChromaDB + Flask app"
	@echo "  all-down   - Stop all containers"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

shell:
	docker compose exec flask-app /bin/bash

restart:
	docker compose restart

clean:
	docker compose down --rmi local -v

db-up:
	docker compose -f docker-compose.chromadb.yml up -d

db-down:
	docker compose -f docker-compose.chromadb.yml down

db-logs:
	docker compose -f docker-compose.chromadb.yml logs -f

db-shell:
	docker compose -f docker-compose.chromadb.yml exec chromadb /bin/sh

all-up: db-up up
	@echo "All services started!"
	@echo "  - ChromaDB: http://localhost:$(CHROMA_EXTERNAL_PORT)"
	@echo "  - App: http://localhost:$(APP_PORT)"

all-down: down db-down
	@echo "All services stopped!"
