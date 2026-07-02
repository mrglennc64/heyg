.PHONY: up down build logs models demo

up:            ## start the full stack
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

models:        ## download all model weights (~12 GB)
	bash infra/models/download_models.sh

demo:          ## fire the example request
	curl -sS -X POST http://localhost:8000/api/v1/generate-avatar-video \
	  -H "Content-Type: application/json" \
	  -H "X-Api-Key: $${FORGE_API_KEY}" \
	  -d @examples/request.json | python -m json.tool
