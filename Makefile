DTMI_PATH := .

include $(DTMI_PATH)/.env
export

.PHONY: help build up down logs shell restart clean db-up db-down db-logs db-shell dev-up dev-down prod-up prod-down nginx-install nginx-reload test-wablas

help:
	@echo Optima Flask App - Docker Commands
	@echo Usage: make [target]

# --- Docker Operations ---

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail 100

shell:
	docker compose exec flask-app /bin/bash

restart:
	docker compose restart

clean:
	docker compose down --rmi local -v

# --- Database (ChromaDB) ---

db-up:
	docker compose -f docker-compose.chromadb.yml up -d

db-down:
	docker compose -f docker-compose.chromadb.yml down

db-logs:
	docker compose -f docker-compose.chromadb.yml logs -f --tail 100

db-shell:
	docker compose -f docker-compose.chromadb.yml exec chromadb /bin/sh

# --- Environments ---

dev-up: db-up
	docker compose up -d
	@echo Dev mode started on port $(APP_PORT)

dev-down: down db-down
	@echo Dev stopped!

prod-up: db-up
	docker compose -f docker-compose.yml up -d
	@echo Prod mode started

prod-down: down db-down

# --- Wablas ---

# Connection diagnostic. Send real msg:  make test-wablas PHONE=628xxxxxxxxxx
test-wablas:
	docker compose exec flask-app python test_wablas.py $(PHONE)

# --- Nginx (Linux only) ---

nginx-install:
	@echo Installing Nginx configs...
	sudo cp nginx.conf /etc/nginx/sites-available/dtmi
	sudo ln -sf /etc/nginx/sites-available/dtmi /etc/nginx/sites-enabled/dtmi
	sudo chmod 644 backsoon.html
	@echo Nginx setup complete for $(DTMI_PATH)

nginx-reload:
	sudo nginx -t && sudo systemctl reload nginx
	@echo Nginx reloaded
