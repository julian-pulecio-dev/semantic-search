# Semantic Search

Keyword search fails when meaning matters. Searching "contract termination clauses" won't match a document that says "either party may end this agreement" — even though they mean the same thing.

Semantic Search solves this by converting documents into vector embeddings and retrieving results by meaning, not exact words. It handles the full pipeline: upload a PDF, and the system automatically parses, chunks, and embeds it. Queries are embedded at search time and matched against stored vectors using cosine similarity.

Built to production standards: event-driven async processing on AWS, horizontal autoscaling, JWT auth, and infrastructure fully defined in Terraform.

---

## Key Features

- **Semantic retrieval** — pgvector HNSW cosine-distance index over 1024-dim embeddings
- **Async ingestion pipeline** — S3 → EventBridge → SQS → ECS worker; API returns immediately
- **Scalable workers** — thread pool with SQS heartbeat extension; graceful `SIGTERM` shutdown
- **Horizontal autoscaling** — ECS web service scales on ALB request count; doc-chunking worker scales on SQS queue depth
- **Production infrastructure** — VPC, RDS, ALB, Secrets Manager, CloudWatch, all in Terraform
- **JWT authentication** — write endpoints require a valid access token; chunk retrieval and semantic search are publicly accessible
- **Bounding polygons** — each chunk carries convex-hull coordinates per page; overlapping chunks share the same page region so polygons stack visually with semi-transparent rendering
- **CI/CD pipeline** — GitHub Actions builds, tests, migrates, and deploys on every push to `main`

---

## Architecture

```
┌─────────────┐    upload     ┌─────────────┐    S3 event    ┌─────────────────┐
│   Client    │ ────────────▶ │  Django API │ ──────────────▶│   EventBridge   │
└─────────────┘               └─────────────┘                └────────┬────────┘
                                     │                                 │ SQS
                                     │                        ┌────────▼────────┐
                                     │                        │  Doc Chunking   │
                                     │                        │    Worker       │
                                     │                        └────────┬────────┘
                                     │                                 │ embeddings
                                     ▼                                 ▼
                               ┌─────────────┐               ┌─────────────────┐
                               │  PostgreSQL  │ ◀─────────── │    pgvector     │
                               │  (RDS)      │               └─────────────────┘
                               └─────────────┘
```

**AWS Services:** ECS Fargate · RDS PostgreSQL · S3 · SQS · EventBridge · Secrets Manager · ALB · CloudWatch

---

## Stack

| Layer | Technology |
|---|---|
| API | Django 4.1 + Django REST Framework |
| Auth | JWT (djangorestframework-simplejwt) |
| Database | PostgreSQL + pgvector (1024-dim embeddings, HNSW index) |
| Embeddings | Amazon Titan Embed Text v2 (via Bedrock) |
| LLM | Amazon Nova (via Bedrock) |
| Document parsing | pdfplumber |
| Background jobs | SQS + custom worker (thread pool) |
| Infrastructure | Terraform (ECS Fargate, RDS, S3, SQS, ALB) |
| CI/CD | GitHub Actions → Docker Hub → ECS |

---

## Document Ingestion Pipeline

1. Client uploads a document via `POST /api/document/`
2. File is stored in S3
3. S3 emits an event → EventBridge routes it to SQS
4. The **doc-chunking** ECS worker picks up the SQS message
5. Worker downloads the file, parses it with pdfplumber, and splits it into chunks
6. Each chunk is embedded with Amazon Titan Embed Text v2 (1024 dimensions)
7. Embeddings are stored in PostgreSQL via pgvector with an HNSW cosine-distance index
8. Document status is updated to `PROCESSED`

## Semantic Search Flow

1. Client sends a query via `POST /api/chunk/search/` (no authentication required)
2. Query text is embedded using Amazon Titan Embed Text v2
3. pgvector executes a cosine-distance search over the HNSW index
4. All chunks whose cosine similarity meets or exceeds `threshold` are returned, ranked by similarity, across all documents

### Example

```
POST /api/chunk/search/

{
  "query": "termination clauses in contracts",
  "threshold": 0.75
}
```

```json
[
  {
    "id": "a3f1c2d4-...",
    "document": "b7e9f012-...",
    "chunk_index": 4,
    "content": "Either party may terminate this agreement upon 30 days written notice...",
    "bounding_polygons": [
      {
        "page_number": 1,
        "points": [[120, 340], [480, 340], [480, 390], [120, 390]]
      }
    ],
    "created_at": "2024-11-15T10:23:44Z"
  },
  ...
]
```

`threshold` is a float between `0.0` and `1.0` (default `0.8`). A higher value returns only closer matches; `0.0` returns all chunks regardless of similarity.

Cosine similarity is derived from pgvector's `CosineDistance` as `similarity = 1 − distance`. Only chunks with `distance ≤ 1 − threshold` are returned.

---

## Design Decisions

### pgvector over a dedicated vector database (Pinecone, Weaviate)
Keeps embeddings colocated with document metadata in a single Postgres transaction. No additional managed service, no eventual-consistency edge cases between vector and relational stores, and lower cost at the scale this project targets.

### SQS over Celery
SQS is a managed AWS service — no broker (Redis/RabbitMQ) to provision, patch, or monitor. It integrates natively with EventBridge for S3-triggered ingestion and with ECS Application Autoscaling for queue-depth-based worker scaling. Celery would add operational overhead without adding capability here.

### HNSW over IVFFlat
HNSW delivers better recall at low latency and does not require a `VACUUM` / `ANALYZE` after bulk inserts to maintain index quality. The trade-off is higher memory usage, which is acceptable for this dataset size.

### Custom worker over AWS Lambda
The chunking worker uses a thread pool with SQS visibility-timeout heartbeat extension. Lambda's 15-minute limit and cold-start overhead make it poorly suited for long PDF parsing jobs. An always-on ECS task avoids both constraints.

---

## Scaling Characteristics

### Web service (ECS Fargate)
Scales on `ALBRequestCountPerTarget`:

| Parameter | Value |
|---|---|
| `min_capacity` | 2 tasks |
| `max_capacity` | 10 tasks |
| `requests_per_target` | 1000 req/min |
| Scale-out cooldown | 60 s |
| Scale-in cooldown | 300 s |

The 60-second scale-out cooldown means new capacity is available within ~2 minutes of a traffic spike (cooldown + task startup).

### Doc-chunking worker (ECS Fargate)
Scales on SQS queue depth (`ApproximateNumberOfMessagesVisible`). A backlog of pending documents triggers additional worker tasks; the thread pool within each task handles burst parallelism at the message level.

### Database
RDS is the current vertical scaling boundary. pgvector's HNSW index keeps search latency sub-100ms at tens of millions of vectors. Horizontal read scaling (read replicas) can be added at the Terraform layer without application changes.

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/token/` | — | Obtain JWT token pair |
| `POST` | `/api/token/refresh/` | — | Refresh access token |
| `POST` | `/api/token/verify/` | — | Verify token |
| `*` | `/api/user/` | Required | User management |
| `*` | `/api/document/` | Required | Document CRUD + upload |
| `*` | `/api/document_type/` | Required | Document type management |
| `*` | `/api/upload_session/` | Required | Upload session tracking |
| `GET` | `/api/chunk/documents/{id}/chunks/` | — | List chunks for a document |
| `GET` | `/api/chunk/chunks/{id}/` | — | Retrieve a single chunk |
| `PATCH` | `/api/chunk/chunks/{id}/refresh/` | Required | Refresh chunk content from polygon |
| `POST` | `/api/chunk/search/` | — | Semantic search across all documents |
| `GET` | `/api/schema/swagger/` | — | Swagger UI |
| `GET` | `/api/schema/redoc/` | — | ReDoc UI |

---

## Local Development

### Prerequisites

- Docker + Docker Compose
- AWS credentials (for S3/Bedrock access)

### Setup

```bash
# 1. Copy and fill in environment variables
cp .env.local.example .env.local

# 2. Start services (Django + PostgreSQL)
docker-compose up

# The API will be available at http://localhost:8000
```

The container auto-runs migrations on startup.

### Run tests

```bash
docker-compose -f docker-compose.ci.yml run --rm semantic-search python manage.py test
```

### Environment variables

| Variable | Description |
|---|---|
| `POSTGRES_USER` | PostgreSQL container user (matches `DB_USER`) |
| `POSTGRES_DB` | PostgreSQL container database name (matches `DB_NAME`) |
| `DB_NAME` | Database name used by Django |
| `DB_HOST` | Database host (use the Docker Compose service name locally, e.g. `semantic-search-db`) |
| `DB_PORT` | Database port (default `5432`) |
| `S3_BUCKET_NAME` | S3 bucket for document storage |
| `AWS_ACCESS_KEY_ID` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials |
| `AWS_DEFAULT_REGION` | AWS region (default `us-east-1`) |

---

## Workers

Workers are located in `app/workers/` and run as separate ECS tasks.

### Document Chunking Worker

```bash
# Entrypoint
python -m workers.document_chunking.run
```

| Environment Variable | Default | Description |
|---|---|---|
| `SQS_QUEUE_URL` | required | SQS queue URL to poll |
| `MAX_WORKERS` | `4` | Thread pool size |
| `VISIBILITY_TIMEOUT` | `300` | SQS message visibility timeout (seconds) |

The worker uses a thread pool with heartbeat extension to prevent message redelivery on long-running tasks, and handles graceful shutdown on `SIGTERM`/`SIGINT`.

---

## Infrastructure

Infrastructure is defined in Terraform under `terraform/`.

### Modules

| Module | Description |
|---|---|
| `vpc` | VPC, subnets, internet gateway, route tables, security groups |
| `rds` | PostgreSQL RDS instance |
| `s3` | Document storage bucket |
| `sqs` | Message queue for document events |
| `eventbridge` | S3 → SQS event routing rules |
| `ecs_web` | Django API service (ECS Fargate + ALB + autoscaling) |
| `ecs_doc_chunking` | Document chunking worker (ECS Fargate + SQS autoscaling) |

### Prerequisites

- Terraform >= 1.0
- AWS CLI configured with credentials that have permissions to manage ECS, RDS, S3, SQS, VPC, ALB, Secrets Manager, EventBridge, and IAM resources
- The following secrets must exist in AWS Secrets Manager **before** running `apply`:
  - `semantic-search/db-user` — plain-text DB username
  - `semantic-search/db-password` — plain-text DB password
- An S3 bucket named `terraform-state-semantic-search` must exist for the remote backend

### Terraform variables

Variables are defined in `terraform/terraform.tfvars`:

| Variable | Value | Description |
|---|---|---|
| `name` | `semantic-search` | Prefix for all named AWS resources |
| `db_name` | `semanticsearch` | PostgreSQL database name |
| `db_user_secret_name` | `semantic-search/db-user` | Secrets Manager secret for DB username |
| `db_password_secret_name` | `semantic-search/db-password` | Secrets Manager secret for DB password |
| `ecs_desired_count` | *(optional)* | Override task count for both ECS services; defaults to module-level values when `null` |

### Deployment

```bash
cd terraform

# 1. Initialize the backend (only needed once, or after adding new modules)
terraform init -backend-config=backend-prod.hcl

# 2. Preview the changes
terraform plan -var-file=terraform.tfvars

# 3. Apply — provisions all AWS resources
terraform apply -var-file=terraform.tfvars
```

After a successful apply the ALB DNS name is available in the Terraform outputs:

```bash
terraform output
```

### Destruction

> **Important:** ECS Fargate services must be scaled to 0 tasks before destroy, otherwise Terraform cannot delete the ECS services and the operation will time out. Use the provided destroy script — it handles the scale-down step automatically before running `terraform destroy`.

**PowerShell:**
```powershell
.\terraform\scripts\destroy\destroy.ps1
```

**Bash:**
```bash
./terraform/scripts/destroy/destroy.sh
```

The script:
1. Scales all ECS tasks down to 0 (`ecs_desired_count=0`)
2. Runs `terraform destroy -var-file=terraform.tfvars`

Resources **not** destroyed by `terraform destroy` (created outside Terraform):
- The S3 remote-state bucket (`terraform-state-semantic-search`)
- The Secrets Manager secrets (`semantic-search/db-user`, `semantic-search/db-password`)

---

## CI/CD

GitHub Actions workflows are defined in `.github/workflows/`.

| Workflow | Trigger | Actions |
|---|---|---|
| `checks.yml` | Every push | Build → run migrations → run tests |
| `deploy.yaml` | Push to `main` | Build image → push to Docker Hub → run ECS migration task → force ECS service update |

The deploy workflow:
1. Pushes the image to Docker Hub (`julianpuleciodev/semantic-search`)
2. Runs `manage.py migrate` as a one-off ECS task and waits for completion
3. Force-deploys the updated image to the ECS web service
