.ONESHELL:
DTMI_PATH := /var/www/html/dtmi
SHELL := /bin/bash

include .env
export

.PHONY: help build up down logs shell restart clean db-up db-down db-logs db-shell dev-up dev-down prod-up prod-down nginx-install nginx-reload

# Helper to avoid typing cd everywhere
define setup_env
	cd $(DTMI_PATH)
endef

help:
	@echo "Optima Flask App - Docker Commands"
	@echo "Usage: make [target]"

# --- Docker Operations ---

build:
	$(setup_env)
	docker compose build

up:
	$(setup_env)
	docker compose up -d

down:
	$(setup_env)
	docker compose down

logs:
	$(setup_env)
	docker compose logs -f

shell:
	$(setup_env)
	docker compose exec flask-app /bin/bash

restart:
	$(setup_env)
	docker compose restart

clean:
	$(setup_env)
	docker compose down --rmi local -v

# --- Database (ChromaDB) ---

db-up:
	$(setup_env)
	docker compose -f docker-compose.chromadb.yml up -d

db-down:
	$(setup_env)
	docker compose -f docker-compose.chromadb.yml down

db-logs:
	$(setup_env)
	docker compose -f docker-compose.chromadb.yml logs -f

db-shell:
	$(setup_env)
	docker compose -f docker-compose.chromadb.yml exec chromadb /bin/sh

# --- Environments ---

dev-up: db-up
	$(setup_env)
	docker compose up -d
	@echo "Dev mode started on port $(APP_PORT)"

dev-down: down db-down
	@echo "Dev stopped!"

prod-up: db-up
	$(setup_env)
	docker compose -f docker-compose.yml up -d
	@echo "Prod mode started"

prod-down: down db-down

# --- Nginx ---

nginx-install:
	$(setup_env)
	@echo "Installing Nginx configs..."
	# We copy from the local folder (where you are) to the system Nginx folders
	sudo cp nginx.conf /etc/nginx/sites-available/dtmi
	sudo ln -sf /etc/nginx/sites-available/dtmi /etc/nginx/sites-enabled/dtmi
	
	# Since backsoon.html is already in $(DTMI_PATH), 
	# we just ensure permissions are correct instead of copying it to itself.
	sudo chmod 644 backsoon.html
	@echo "Nginx setup complete for $(DTMI_PATH)"

nginx-reload:
	sudo nginx -t && sudo systemctl reload nginx
	@echo "Nginx reloaded"