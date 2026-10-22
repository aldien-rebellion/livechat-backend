# Master Architecture Blueprint: Real-Time Live Chat Platform
> **Repository Strategy:** Clean Monorepo (`backend/` + `frontend/`)  
> **Deployment Target:** AWS EC2 + Docker Compose + Nginx + Let's Encrypt  
> **Team Collaboration Focus:** Modular component-based development without merge conflicts

---

## 1. System Architecture Overview

```mermaid
flowchart TD
    subgraph Clients["Clients Layer"]
        Web["💻 React Web Client (Vite + Tailwind CSS)<br/>• Workspace-level Persistent WebSocket (`/ws`)<br/>• Axios Client with JWT Auto-Refresh Interceptor"]
        K6["⚡ k6 Load Tester (WebSocket + HTTP RPS)"]
        Playwright["🎭 Playwright E2E Test Suite"]
    end

    subgraph AWS_EC2["☁️ AWS EC2 Instance (Docker Compose Network: livechat_net)"]
        Nginx["🌐 Nginx (Reverse Proxy & Ingress)<br/>• Ports: 80 / 443 (SSL Certbot)<br/>• Static Frontend Assets Serving (`/`)<br/>• API Routing (`/api/v1/*`)<br/>• WebSocket Upgrade Tunnel (`/ws`)<br/>• Media Uploads Volume (`/uploads/`)"]

        subgraph CoreAPI["🚀 FastAPI Backend Cluster"]
            API["FastAPI Async Application<br/>• Dual-token Auth (Access 30m / Refresh 7d)<br/>• Workspace WebSocket Hub (`/ws`)<br/>• Message Search Engine (PostgreSQL tsvector)<br/>• Prometheus Metrics (`/metrics`)"]
        end

        subgraph DataTier["💾 Databases & Storage Tier"]
            PG[("🐘 PostgreSQL 15+<br/>• Clean Live Chat Domain Models<br/>• Full-Text Search (tsvector + GIN Index)<br/>• Read Receipts & Threads")]
            Redis[("⚡ Redis 7+<br/>• Channel Pub/Sub Broker<br/>• Presence Heartbeat (TTL 60s)<br/>• Online/Offline Workspace Sets")]
            Storage["📁 Storage Engine<br/>• Local Volume: `/app/uploads`<br/>• Swappable to AWS S3 via .env"]
        end

        subgraph Observability["📊 Monitoring & Observability"]
            Prom["📈 Prometheus (Scrape /metrics 15s)"]
            Graf["📊 Grafana Dashboard (WS Connections, RPS, Latency)"]
        end
    end

    Web -->|HTTPS / WSS| Nginx
    K6 -->|Load Test Traffic| Nginx
    Playwright -->|E2E Test Flow| Nginx

    Nginx -->|Proxy Pass| API
    API -->|Async SQLAlchemy 2.0| PG
    API <-->|Pub/Sub & Presence| Redis
    API -->|Store / Retrieve Files| Storage
    Prom -->|Scrape| API
    Prom --> Graf
```

---

## 2. Directory Structure for the 2 Repositories

### 2.1 Repository 1: `livechat-backend`
```text
livechat-backend/
├── .github/
│   └── workflows/
│       ├── ci.yml               # Backend CI: Lint (flake8) + Pytest (Postgres & Redis services)
│       └── cd.yml               # Backend CD: SSH deploy to AWS EC2 (git pull & docker compose restart)
├── alembic/                     # Database migrations (clean livechat domain)
├── app/
│   ├── config/                  # Settings (pydantic-settings), metrics, security
│   ├── controllers/             # REST Controllers & WebSocket endpoint (/ws)
│   ├── db/                      # Async engine & sessionmaker (SQLAlchemy 2.0)
│   ├── models/                  # Pure domain models (User, Workspace, Channel, Message, etc.)
│   ├── schemas/                 # Pydantic v2 schemas & search queries
│   ├── services/                # Business logic (Auth, ChatPubSub, SearchService, Presence)
│   └── main.py                  # FastAPI application factory & router mounting
├── tests/
│   ├── conftest.py              # Async test fixtures (database, redis, auth clients)
│   ├── test_auth.py
│   ├── test_chat_search.py      # Tests for tsvector full-text search
│   └── test_websocket.py
├── infra/                       # EC2 Terraform scripts & cloud-init provisioning
├── nginx/                       # Reverse proxy configuration
├── Dockerfile
├── requirements.txt
├── alembic.ini
├── docker-compose.yml           # Production & staging stack (Postgres, Redis, API, Frontend, Nginx)
├── .env.example
└── README.md
```

### 2.2 Repository 2: `livechat-frontend`
```text
livechat-frontend/
├── .github/
│   └── workflows/
│       ├── ci.yml               # Frontend CI: Type Check (tsc) + Lint + Build Verification
│       └── cd.yml               # Frontend CD: SSH deploy to AWS EC2 (git pull /opt/livechat-frontend & rebuild)
├── src/
│   ├── components/              # Reusable UI (Sidebar, ChannelList, ChatArea, MessageItem)
│   ├── contexts/                # AuthContext (Token auto-refresh), WebSocketContext
│   ├── hooks/                   # useWebSocket, usePresence, useSearch
│   ├── services/                # Axios API client & WebSocket transport
│   ├── pages/                   # Login, Register, Workspace, ChannelView
│   └── App.tsx
├── public/
├── Dockerfile                   # Multi-stage build with Nginx for production
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
└── README.md
```

---

## 3. Key Technical Decisions & Upgrades

### 3.1 Workspace-Level WebSocket Protocol (`/ws`)
- **Single Connection:** Client connects to `/ws?token=<access_token>` once per session.
- **Client Frame Action:**
  - `{"action": "subscribe", "channel_id": "..."}`
  - `{"action": "send_message", "channel_id": "...", "content": "Hello team!"}`
  - `{"action": "typing", "channel_id": "..."}`
  - `{"action": "read_receipt", "message_id": "..."}`
  - `{"action": "heartbeat"}` (Keeps online status alive in Redis for 60s)
- **Redis Fanout Broker:** When FastAPI receives a message, it publishes to Redis channel `pubsub:channel:{channel_id}` so all API instances broadcast to subscribed clients.

### 3.2 Full-Text Search with PostgreSQL `tsvector`
To achieve instant Slack-like search across historical messages:
```sql
-- Migration snippet
ALTER TABLE messages ADD COLUMN search_vector tsvector;

-- Auto-generated tsvector on insert/update
CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE
ON messages FOR EACH ROW EXECUTE FUNCTION
tsvector_update_trigger(search_vector, 'pg_catalog.english', content);

-- GIN index for ultra-fast text search
CREATE INDEX idx_messages_search_vector ON messages USING GIN(search_vector);
```
FastAPI search endpoint:
```python
# app/services/search_service.py
from sqlalchemy import select, func

async def search_messages(db: AsyncSession, channel_id: uuid.UUID, query: str, limit: int = 30):
    stmt = (
        select(Message)
        .where(
            Message.channel_id == channel_id,
            Message.search_vector.op("@@")(func.plainto_tsquery("english", query))
        )
        .order_by(
            func.ts_rank(Message.search_vector, func.plainto_tsquery("english", query)).desc(),
            Message.created_at.desc()
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()
```

### 3.3 Dual-Token JWT Authentication Flow
1. **Login:** `POST /api/v1/auth/login` returns `{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }`.
   - Access Token: TTL 30 minutes.
   - Refresh Token: TTL 7 days (hashed and stored in PostgreSQL / Redis).
2. **Auto-Refresh Interceptor:** Frontend Axios interceptor intercepts HTTP 401, calls `POST /api/v1/auth/refresh`, updates the tokens, and retries the failed request seamlessly.
3. **WebSocket Reconnect:** If WebSocket disconnects due to token expiration, client fetches fresh access token and reconnects with exponential backoff.

### 3.4 Dual-Backend Storage Engine
```python
# app/services/storage_service.py
class StorageService:
    @staticmethod
    async def upload_file(file_bytes: bytes, filename: str) -> str:
        if settings.STORAGE_BACKEND == "s3":
            # Upload to AWS S3 bucket via aioboto3
            return s3_url
        else:
            # Save to /app/uploads volume served by Nginx
            return local_path
```

---

## 4. CI/CD Pipeline & Cloud Automated Deployment (อ้างอิง Workshop 11 & 12)

ระบบจัดโครงสร้าง CI และ CD ให้สอดคล้องตามมาตรฐาน **Workshop 11 (Build the Assembly Line)** และ **Workshop 12 (To the Cloud!)** โดยคำนึงถึงข้อจำกัดของทรัพยากรเซิร์ฟเวอร์คลาวด์ (1 vCPU, 1GB RAM / t3.small):
* **CI (Continuous Integration):** ทำงานทันทีเมื่อเปิด Pull Request (PR) เข้าสู่ `main` เพื่อรัน Linter และ Automated Tests ป้องกันโค้ดพังก่อนการ Merge (Workshop 11 กิจกรรมที่ 1)
* **CD (Continuous Deployment):** ทำงานเมื่อโค้ดถูก Merge สู่ `main` โดยแบ่งเป็น 2 Jobs:
  1. `build-and-push`: ใช้ GitHub Actions Runner สเปกสูงเป็นคน Build Docker Image แล้ว Push ขึ้น **Docker Hub** พร้อมแท็ก `:latest` และ `:${{ github.sha }}` (Workshop 11 กิจกรรมที่ 3)
  2. `deploy-to-server`: SSH ไปยัง Cloud Instance เพื่อรัน `docker pull` และ `docker-compose up -d --remove-orphans` (Workshop 12 กิจกรรมที่ 3)
  > [!NOTE]
  > **ทำไมจึงไม่สั่ง build บนคลาวด์ตรงๆ?** เซิร์ฟเวอร์ขนาดเล็ก (1 vCPU, 1GB RAM) หากต้องรันคำสั่ง `docker build` (เช่น คอมไพล์ C dependencies หรือบันเดิล Node/Vite) อาจทำให้ CPU พุ่ง 100% และเกิดปัญหา Memory OOM (Out Of Memory) จนเครื่องค้างได้ การผลักภาระ Build ให้ GitHub Actions แล้วเซิร์ฟเวอร์ทำเพียง `docker pull` จึงเป็นวิธีที่มีประสิทธิภาพและเสถียรที่สุด

### ตาราง GitHub Secrets ส่วนกลางที่ต้องเตรียม (Workshop 11 & 12)

| Secret Name | คำอธิบาย | แหล่งที่มา |
| :--- | :--- | :--- |
| `DOCKERHUB_USERNAME` | Username ของบัญชี Docker Hub | [Docker Hub Profile](https://hub.docker.com/) |
| `DOCKERHUB_TOKEN` | Personal Access Token (Read/Write) | Docker Hub Security -> New Access Token |
| `SERVER_HOST` | Public IP ของเซิร์ฟเวอร์ Cloud | ได้รับจากผลลัพธ์การรัน Terraform (`outputs.tf`) |
| `SERVER_USER` | ชื่อผู้ใช้ SSH ของเครื่องเซิร์ฟเวอร์ (เช่น `ubuntu`) | กำหนดใน OS Image ของ Cloud Instance |
| `SSH_PRIVATE_KEY` | Private SSH Key สำหรับสั่งการเซิร์ฟเวอร์ | กุญแจคู่กับ Public Key ที่บันทึกไว้ใน `~/.ssh/authorized_keys` |

---

### 4.1 Backend Pipelines (`livechat-backend`)

#### 4.1.1 Continuous Integration (`.github/workflows/ci.yml`)
ทำงานเมื่อเปิด Pull Request หรือ Push เข้า `main` เพื่อตรวจสอบคุณภาพโค้ดและรัน Automated Tests
```yaml
name: Backend CI

on:
  pull_request:
    branches: [ main ]
  push:
    branches: [ main ]

jobs:
  test:
    name: Lint & Automated Tests
    runs-on: ubuntu-latest
    timeout-minutes: 10

    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: livechat_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Lint with flake8
        run: |
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
          flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

      - name: Run Pytest
        env:
          DATABASE_URL: postgresql+asyncpg://test_user:test_password@localhost:5432/livechat_test
          REDIS_URL: redis://localhost:6379/0
        run: |
          pytest
```

#### 4.1.2 Continuous Deployment (`.github/workflows/cd.yml`)
ทำงานเมื่อ Merge โค้ดเข้า branch `main` โดย Build และ Push ขึ้น Docker Hub จากนั้น SSH ไป Deploy บน Cloud Server
```yaml
name: Backend CD

on:
  push:
    branches: [ main ]

jobs:
  build-and-push:
    name: Build & Push Backend Image to Docker Hub
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and Push Docker Image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile
          push: true
          tags: |
            ${{ secrets.DOCKERHUB_USERNAME }}/livechat-backend:latest
            ${{ secrets.DOCKERHUB_USERNAME }}/livechat-backend:${{ github.sha }}

  deploy-to-server:
    name: Deploy to Cloud Server via SSH
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - name: SSH to Server and Update Container
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/livechat-server
            docker pull ${{ secrets.DOCKERHUB_USERNAME }}/livechat-backend:latest
            docker compose up -d --remove-orphans backend
            docker compose exec -T backend alembic upgrade head
```

---

### 4.2 Frontend Pipelines (`livechat-frontend`)

#### 4.2.1 Continuous Integration (`.github/workflows/ci.yml`)
ทำงานเมื่อเปิด Pull Request หรือ Push เข้า `main` เพื่อตรวจ Type Check, Lint และทดสอบ Build ของ React + Vite
```yaml
name: Frontend CI

on:
  pull_request:
    branches: [ main ]
  push:
    branches: [ main ]

jobs:
  verify:
    name: Lint, Type Check & Build
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Type Check & Lint
        run: |
          npx tsc --noEmit
          npm run lint

      - name: Build Verification
        run: npm run build
```

#### 4.2.2 Continuous Deployment (`.github/workflows/cd.yml`)
ทำงานเมื่อ Merge โค้ดเข้า branch `main` โดย Build Docker Image (Vite Multi-stage Nginx) ส่งขึ้น Docker Hub และสั่ง Deploy บนเซิร์ฟเวอร์
```yaml
name: Frontend CD

on:
  push:
    branches: [ main ]

jobs:
  build-and-push:
    name: Build & Push Frontend Image to Docker Hub
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and Push Docker Image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile
          push: true
          tags: |
            ${{ secrets.DOCKERHUB_USERNAME }}/livechat-frontend:latest
            ${{ secrets.DOCKERHUB_USERNAME }}/livechat-frontend:${{ github.sha }}

  deploy-to-server:
    name: Deploy to Cloud Server via SSH
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - name: SSH to Server and Update Container
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/livechat-server
            docker pull ${{ secrets.DOCKERHUB_USERNAME }}/livechat-frontend:latest
            docker compose up -d --remove-orphans frontend
```

---

## 5. Summary of What to Keep vs What to Redirect

| Item | Status in New Repo | Rationale |
| :--- | :--- | :--- |
| **FastAPI + Async SQLAlchemy 2.0** | **Retain (คงเดิม)** | High performance, async database pooling (`asyncpg`). |
| **Redis Pub/Sub & Presence** | **Retain & Upgrade** | Reliable sliding heartbeat (TTL 60s) and multi-node broadcast. |
| **Prometheus & Grafana** | **Retain (คงเดิม)** | Industry-standard observability ready for production. |
| **k6 Load Testing** | **Retain (คงเดิม)** | Verifies high concurrency before presenting to stakeholders. |
| **Telemetry, Devices, RabbitMQ** | **Remove (ตัดออก 100%)** | Clutter from earlier workshops; live chat should be 100% domain focused. |
| **Single-file `client.html`** | **Redirect to React + Vite** | Component-based frontend prevents merge conflicts across team members. |
| **Channel-level WS Endpoint** | **Redirect to Workspace `/ws`** | Eliminates reconnect latency when switching channels. |
| **Message Search** | **New Feature (PostgreSQL tsvector)** | Native full-text search with zero external search engine overhead. |
| **Cloud Deployment** | **New (AWS EC2 + Automated CI/CD)** | Production live link accessible anywhere with SSL. |
