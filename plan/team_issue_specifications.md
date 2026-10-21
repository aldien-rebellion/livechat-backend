# GitHub Issues Specification: Real-Time Live Chat Platform
> **จุดประสงค์:** รายละเอียดเนื้องาน สัญญาเชื่อมต่อ (API Contract), โครงสร้างตาราง (Schema) และรูปแบบข้อมูล (Payload) อ้างอิงตามเลข Issue จริงบน GitHub (Backend #1–#15 และ Frontend #1–#9)

---

## สารบัญข้อตกลงกลางของโปรเจกต์ (Shared Contracts)

* **Backend Port & Base URL:** `http://localhost:8000/api/v1`
* **WebSocket URL:** `ws://localhost:8000/ws?token=<access_token>`
* **Database Connection:** `postgresql+asyncpg://postgres:postgres@localhost:5432/livechat_db`
* **Redis Connection:** `redis://localhost:6379/0`
* **JWT Contract:** Algorithm `HS256`, Access Token TTL `30m`, Refresh Token TTL `7d`

---

# 📦 REPO 1: `livechat-backend`

---

### [Backend #1] [DevOps] สร้าง Dockerfile ของ Backend (Python 3.11-slim)
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 1 (ทำได้ทันที)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  EXPOSE 8000
  CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
  ```

---

### [Backend #2] [Infrastructure] สร้าง docker-compose.yml ควบคุม Nginx, Postgres, Redis, API และ Frontend
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 1 (สำคัญที่สุด เปิดทางให้ทุกคน)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  ```yaml
  version: '3.8'
  services:
    postgres:
      image: postgres:15-alpine
      container_name: livechat_postgres
      environment:
        POSTGRES_USER: postgres
        POSTGRES_PASSWORD: postgres
        POSTGRES_DB: livechat_db
      ports:
        - "5432:5432"
      volumes:
        - postgres_data:/var/lib/postgresql/data

    redis:
      image: redis:7-alpine
      container_name: livechat_redis
      ports:
        - "6379:6379"
      volumes:
        - redis_data:/data

  volumes:
    postgres_data:
    redis_data:
  ```

---

### [Backend #3] [Cloud] Provision AWS EC2 Instance และตั้งค่า Security Group (Port 80, 443, 22)
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 1 (ทำได้ทันที)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สร้าง EC2 Instance: OS Ubuntu 22.04 LTS (t3.small หรือ t3.medium)
  2. ตั้งค่า Inbound Security Group:
     - Port 22 (SSH)
     - Port 80 (HTTP)
     - Port 443 (HTTPS)
  3. ติดตั้ง Docker Engine และ Docker Compose Plugin บน EC2
  4. สร้าง SSH Key Pair สำหรับเชื่อมต่อจาก GitHub Actions

---

### [Backend #6] [Database] ออกแบบ Data Models ด้วย SQLAlchemy 2.0 (Users, Workspaces, Channels, Messages)
* **ผู้รับผิดชอบ:** `[คนที่ 3 {Database Lead}]`
* **ลำดับการทำงาน:** Step 1 (ทำได้ทันที)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * โมเดลที่ต้องสร้างใน `app/models/`:
    1. `User`: `id (UUID PK)`, `email (Unique)`, `username (Unique)`, `hashed_password`, `full_name`, `avatar_url`, `is_active`, `created_at`
    2. `Workspace`: `id (UUID PK)`, `name`, `slug (Unique)`, `owner_id (UUID FK -> users.id)`
    3. `WorkspaceMember`: `workspace_id (UUID FK)`, `user_id (UUID FK)`, `role (OWNER/ADMIN/MEMBER)`
    4. `Channel`: `id (UUID PK)`, `workspace_id (UUID FK)`, `name`, `is_private`
    5. `ChannelMember`: `channel_id (UUID FK)`, `user_id (UUID FK)`, `joined_at`
    6. `Message`: `id (UUID PK)`, `channel_id (UUID FK)`, `user_id (UUID FK)`, `content (Text)`, `parent_id (Nullable FK -> messages.id)`, `created_at`
    7. `MessageRead`: `message_id (UUID FK)`, `user_id (UUID FK)`, `read_at`

---

### [Backend #7] [Database] ติดตั้ง Alembic และสร้าง Migration แรกสำหรับสร้าง Tables ทั้งหมด
* **ผู้รับผิดชอบ:** `[คนที่ 3 {Database Lead}]`
* **ลำดับการทำงาน:** Step 2 *(ต้องรอ Backend #2 และ Backend #6)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. ติดตั้ง Alembic: `alembic init -t async alembic`
  2. แก้ไข `alembic/env.py` เชื่อมต่อ `Base.metadata`
  3. สั่งรัน `alembic revision --autogenerate -m "Initial livechat schema"`
  4. สั่งรัน `alembic upgrade head` เพื่อสร้างตารางลงใน Postgres จริง

---

### [Backend #8] [Search Engine] เพิ่มฟิลด์ search_vector (tsvector) ในตาราง messages พร้อมสร้าง Auto-Update Trigger
* **ผู้รับผิดชอบ:** `[คนที่ 3 {Database Lead}]`
* **ลำดับการทำงาน:** Step 3 *(ต้องรอ Backend #7)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  ```sql
  ALTER TABLE messages ADD COLUMN search_vector tsvector;
  CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE ON messages
  FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(search_vector, 'pg_catalog.english', content);
  ```

---

### [Backend #9] [Search Engine] สร้าง GIN Index และเขียนฟังก์ชัน Query ค้นหาข้อความด้วย ts_rank
* **ผู้รับผิดชอบ:** `[คนที่ 3 {Database Lead}]`
* **ลำดับการทำงาน:** Step 3 *(ต้องรอ Backend #8)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สร้าง GIN Index: `CREATE INDEX idx_messages_search_vector ON messages USING GIN(search_vector);`
  2. เขียน Service ค้นหา:
     `SELECT * FROM messages WHERE channel_id = :ch_id AND search_vector @@ plainto_tsquery('english', :q) ORDER BY ts_rank(search_vector, plainto_tsquery('english', :q)) DESC LIMIT 30;`

---

### [Backend #10] [Backend Core] วางโครงสร้างโปรเจกต์ FastAPI, Pydantic v2 Schemas และการจัดการ CORS
* **ผู้รับผิดชอบ:** `[คนที่ 2 {Backend Lead}]`
* **ลำดับการทำงาน:** Step 1 (ทำได้ทันที)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สร้าง `app/main.py` พร้อม CORS `allow_origins=["*"]`
  2. สร้าง Pydantic v2 Schemas ใน `app/schemas/`
  3. ติดตั้ง Prometheus Instrumentator เปิด Endpoint `/metrics`
  4. สร้าง Endpoint `/healthcheck` เช็กสถานะระบบ

---

### [Backend #11] [Auth API] พัฒนาระบบ Dual-Token JWT (/api/v1/auth/login, /api/v1/auth/refresh)
* **ผู้รับผิดชอบ:** `[คนที่ 2 {Backend Lead}]`
* **ลำดับการทำงาน:** Step 3 *(ต้องรอ Backend #7 และ Backend #10)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * `POST /api/v1/auth/register`
  * `POST /api/v1/auth/login` ➡️ คืนค่า `{ access_token, refresh_token, token_type, user }`
  * `POST /api/v1/auth/refresh` ➡️ รับ `{ refresh_token }` คืนค่า Access Token ใหม่

---

### [Backend #12] [WebSocket Hub] สร้าง Workspace-level WebSocket Endpoint (/ws) รองรับ Multiplexing
* **ผู้รับผิดชอบ:** `[คนที่ 2 {Backend Lead}]`
* **ลำดับการทำงาน:** Step 3 *(ต้องรอ Backend #2 และ Backend #10)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * `@app.websocket("/ws")` รับ Token ทาง Query: `/ws?token=<access_token>`
  * รองรับ Actions จาก Client:
    - `{"action": "send_message", "channel_id": "...", "content": "..."}`
    - `{"action": "typing", "channel_id": "..."}`
    - `{"action": "read_receipt", "channel_id": "...", "message_id": "..."}`
    - `{"action": "heartbeat"}`

---

### [Backend #13] [Real-Time Engine] เชื่อมต่อ Redis Pub/Sub เพื่อกระจายข้อความแชทข้าม Client แบบเรียลไทม์
* **ผู้รับผิดชอบ:** `[คนที่ 2 {Backend Lead}]`
* **ลำดับการทำงาน:** Step 3 *(ต้องรอ Backend #12)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * เชื่อมโยง WebSocket กับ Redis Pub/Sub Channel `pubsub:channel:{channel_id}`
  * ส่งต่อ Broadcast Event `new_message`, `user_typing`, `presence_update` ให้ Client ทุกคนที่กำลัง Subscribe อยู่

---

### [Backend #14] [Presence] พัฒนาระบบ Presence Heartbeat (บันทึกสถานะ Online/Offline TTL 60s ลง Redis)
* **ผู้รับผิดชอบ:** `[คนที่ 2 {Backend Lead}]`
* **ลำดับการทำงาน:** Step 3 *(ต้องรอ Backend #12)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * เมื่อได้รับ Action `heartbeat` ให้สั่ง:
    `SET presence:user:{user_id} "online" EX 60`
  * ดึงสถานะ User: เช็กว่า Key ยังมีอยู่ใน Redis หรือไม่

---

### [Backend #4] [CI] วางระบบ GitHub Actions CI (Linting & Automated Tests ด้วย Pytest + Postgres/Redis Services)
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 1 (ทำได้ทันที / Day 1 เพื่อเป็น Guardrail ป้องกันโค้ดพังบนทุก PR)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * สร้าง `.github/workflows/ci.yml`:
    1. Triggers: `pull_request` ไปยัง `main`, `push` ไปยัง `main`
    2. Services: PostgreSQL 15 (`postgres_data`), Redis 7
    3. Steps:
       - Setup Python 3.11 พร้อม cache `pip`
       - ติดตั้ง Dependencies: `pip install -r requirements.txt` และ `pip install flake8 pytest pytest-asyncio httpx`
       - Linting: `flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
       - รัน Pytest: `pytest tests`

---

### [Backend #15] [CD] เขียน GitHub Actions Workflow Deploy Backend สู่ AWS EC2 ผ่าน SSH
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 5 *(ทำเมื่อระบบ Step 1-4 เชื่อมต่อกันแล้ว)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * สร้าง `.github/workflows/cd.yml`:
    1. Trigger: `push` ไปยัง `main` เท่านั้น
    2. ใช้ Action `appleboy/ssh-action@v1.0.3` เชื่อมต่อ EC2 ผ่าน Secrets (`AWS_EC2_HOST`, `AWS_EC2_USER`, `AWS_SSH_PRIVATE_KEY`)
    3. คำสั่ง Deploy:
       ```bash
       cd /opt/livechat-backend
       git pull origin main
       docker compose up -d --build backend
       docker compose exec -T backend alembic upgrade head
       ```

---

### [Backend #5] [Observability & SSL] ติดตั้ง SSL Let's Encrypt (Certbot) และระบบมอนิเตอร์ Prometheus + Grafana
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 5 *(ทำต่อจาก Backend #15 และ Frontend #9)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. ติดตั้ง Certbot Nginx ขอ SSL Certificate เพื่อให้เข้าผ่าน HTTPS และ WSS ได้อย่างปลอดภัย
  2. ติดตั้งคอนเทนเนอร์ Prometheus และ Grafana (พอร์ต 3000) แสดง Dashboard Active WebSockets และ RPS

---

# 📦 REPO 2: `livechat-frontend`

---

### [Frontend #1] [DevOps] สร้าง Dockerfile (Multi-stage Nginx) และตั้งค่า Nginx สำหรับเสิร์ฟไฟล์หน้าเว็บ
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 1 (ทำได้ทันที)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  ```dockerfile
  FROM node:20-alpine AS builder
  WORKDIR /app
  COPY package*.json ./
  RUN npm install
  COPY . .
  RUN npm run build

  FROM nginx:alpine
  COPY --from=builder /app/dist /usr/share/nginx/html
  EXPOSE 80
  CMD ["nginx", "-g", "daemon off;"]
  ```

---

### [Frontend #2] [Setup] ติดตั้งและสร้างโครงสร้างโปรเจกต์ React + Vite + TypeScript + Tailwind CSS
* **ผู้รับผิดชอบ:** `[คนที่ 1 {Frontend Lead}]`
* **ลำดับการทำงาน:** Step 1 (ทำได้ทันที)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. `npm create vite@latest livechat-frontend -- --template react-ts`
  2. ติดตั้ง Tailwind CSS, Lucide Icons, Axios, React Router Dom
  3. จัดโครงสร้างโฟลเดอร์: `components/`, `contexts/`, `pages/`, `services/`

---

### [Frontend #4] [UI Component] พัฒนาส่วน Sidebar และ Workspace / Channel List
* **ผู้รับผิดชอบ:** `[คนที่ 1 {Frontend Lead}]`
* **ลำดับการทำงาน:** Step 2 *(ต้องรอ Frontend #2)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * สร้าง `Sidebar.tsx` แสดงรายชื่อ Workspace
  * สร้าง `ChannelList.tsx` แสดงรายชื่อ Channel พร้อมปุ่มกดสร้างห้องใหม่ (ใส่ Mock Data ก่อนได้)

---

### [Frontend #5] [Chat UI] พัฒนาพื้นที่กล่องแชท ChatArea แสดงประวัติข้อความและกล่องพิมพ์ส่งข้อความ
* **ผู้รับผิดชอบ:** `[คนที่ 1 {Frontend Lead}]`
* **ลำดับการทำงาน:** Step 2 *(ต้องรอ Frontend #2)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * สร้าง `ChatArea.tsx`, `MessageItem.tsx` (แสดง Avatar, ชื่อ, เวลา, ข้อความ)
  * สร้าง `MessageInput.tsx` (กล่องพิมพ์ข้อความ พร้อมส่ง Event เมื่อกด Enter)

---

### [Frontend #3] [Auth UI] ออกแบบหน้าจอ Login / Register และจัดการเก็บ JWT Token ลง State
* **ผู้รับผิดชอบ:** `[คนที่ 1 {Frontend Lead}]`
* **ลำดับการทำงาน:** Step 4 *(ต้องรอ Backend #11)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. ออกแบบหน้า UI Login และ Register
  2. ทำ Axios Auto-refresh Interceptor ดักจับ Token หมดอายุและส่ง Refresh Token อัตโนมัติ

---

### [Frontend #6] [WebSocket Client] เชื่อมต่อ WebSocketContext สำหรับรับส่งข้อความสดและ Typing
* **ผู้รับผิดชอบ:** `[คนที่ 1 {Frontend Lead}]`
* **ลำดับการทำงาน:** Step 4 *(ต้องรอ Backend #12 และ Backend #13)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สร้าง `WebSocketContext.tsx` เชื่อมต่อ `ws://localhost:8000/ws?token=${token}`
  2. รับส่งข้อความสดแบบสองทาง (Two-way communication)
  3. แสดงข้อความ *"กำลังพิมพ์..."* เมื่อได้รับ Event `user_typing`

---

### [Frontend #7] [Search UI] พัฒนาหน้าต่าง Search Modal ค้นหาข้อความย้อนหลังในห้องแชท
* **ผู้รับผิดชอบ:** `[คนที่ 1 {Frontend Lead}]`
* **ลำดับการทำงาน:** Step 4 *(ต้องรอ Backend #9)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. ทำ Search Modal (กดคีย์ลัด `Ctrl + K`)
  2. ยิง API ค้นหา: `GET /api/v1/channels/{id}/search?q={query}`
  3. แสดงผลลัพธ์ข้อความที่ตรงกันและคลิกเพื่อกระโดดไปยังข้อความนั้นได้

---

### [Frontend #8] [CI] วางระบบ GitHub Actions CI (Type Check, Lint และ Build Verification)
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 1 (ทำได้ทันที / Day 1 เพื่อเป็น Guardrail ป้องกันโค้ดพังบนทุก PR)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * สร้าง `.github/workflows/ci.yml`:
    1. Triggers: `pull_request` ไปยัง `main`, `push` ไปยัง `main`
    2. Steps:
       - Setup Node.js 20 พร้อม cache `npm`
       - ติดตั้ง Dependencies ด้วย `npm ci`
       - ตรวจสอบ Type Check: `npx tsc --noEmit`
       - ตรวจสอบ Code Style: `npm run lint`
       - ทดสอบ Build Production: `npm run build`

---

### [Frontend #9] [CD] เขียน GitHub Actions Workflow Deploy Frontend สู่ AWS EC2 ผ่าน SSH
* **ผู้รับผิดชอบ:** `[คนที่ 4 {DevOps Lead}]`
* **ลำดับการทำงาน:** Step 5 *(ทำเมื่อระบบ Step 1-4 เชื่อมต่อกันแล้ว)*
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * สร้าง `.github/workflows/cd.yml`:
    1. Trigger: `push` ไปยัง `main` เท่านั้น
    2. ใช้ Action `appleboy/ssh-action@v1.0.3` เชื่อมต่อ EC2 ผ่าน Secrets (`AWS_EC2_HOST`, `AWS_EC2_USER`, `AWS_SSH_PRIVATE_KEY`)
    3. คำสั่ง Deploy:
       ```bash
       cd /opt/livechat-frontend
       git pull origin main
       cd /opt/livechat-backend
       FRONTEND_CONTEXT=/opt/livechat-frontend docker compose --profile app up -d --build frontend
       ```
