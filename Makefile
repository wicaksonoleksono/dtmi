DTMI_PATH := /var/www/html/dtmi

include $(DTMI_PATH)/.env
export

.PHONY: help build up down logs shell restart clean db-up db-down db-logs db-shell dev-up dev-down prod-up prod-down nginx-install nginx-reload

help:
	@echo "Optima Flask App - Docker Commands"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Development:"
	@echo "  dev-up     - Start in dev mode (hot reload)"
	@echo "  dev-down   - Stop dev containers"
	@echo ""
	@echo "Production:"
	@echo "  prod-up    - Start in prod mode (no reload)"
	@echo "  prod-down  - Stop prod containers"
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
	@echo "Nginx:"
	@echo "  nginx-install - Copy config to sites-available and enable"
	@echo "  nginx-reload  - Test and reload nginx"

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

dev-up: db-up
	docker compose up -d
	@echo "Dev mode started (hot reload enabled)"
	@echo "  - ChromaDB: http://localhost:$(CHROMA_EXTERNAL_PORT)"
	@echo "  - App: http://localhost:$(APP_PORT)"

dev-down: down db-down
	@echo "Dev stopped!"

prod-up: db-up
	docker compose -f docker-compose.yml up -d
	@echo "Prod mode started"
	@echo "  - ChromaDB: http://localhost:$(CHROMA_EXTERNAL_PORT)"
	@echo "  - App: http://localhost:$(APP_PORT)"

prod-down: down db-down
	@echo "Prod stopped!"

nginx-install:
	sudo mkdir -p $(DTMI_PATH)
	sudo cp nginx.conf /etc/nginx/sites-available/dtmi
	sudo ln -sf /etc/nginx/sites-available/dtmi /etc/nginx/sites-enabled/dtmi
	sudo cp backsoon.html $(DTMI_PATH)/backsoon.html
	@echo "Nginx config installed to $(DTMI_PATH)"

nginx-reload:
	sudo nginx -t && sudo systemctl reload nginx
	@echo "Nginx reloaded"
