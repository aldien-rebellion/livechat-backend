# GitHub Issues Specification: Real-Time Live Chat Platform
> **จุดประสงค์:** รายละเอียดเนื้องาน สัญญาเชื่อมต่อ (API Contract), โครงสร้างตาราง (Schema) และรูปแบบข้อมูล (Payload) ของทั้ง 21 Issues เพื่อให้สมาชิกทั้ง 4 คนทำงานคู่ขนานกันได้โดยไม่ติดขัด

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

### [BE-11] [Infrastructure] สร้าง docker-compose.yml สำหรับ Local Development
* **ผู้รับผิดชอบ:** คนที่ 4 (DevOps Lead - ตัวคุณเอง)
* **เป้าหมาย:** สร้างบริการพื้นฐาน (Postgres 15 และ Redis 7) ให้เพื่อนในทีมรันในเครื่องได้ทันที
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
* **Acceptance Criteria:**
  - สั่ง `docker compose up -d` แล้ว Postgres และ Redis สตาร์ตผ่าน พอร์ต 5432 และ 6379 เชื่อมต่อได้

---

### [BE-12] [Cloud] Provision AWS EC2 Instance และตั้งค่า Security Group
* **ผู้รับผิดชอบ:** คนที่ 4 (DevOps Lead - ตัวคุณเอง)
* **เป้าหมาย:** เตรียม Cloud Server บน AWS รองรับการรัน Production
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สร้าง EC2 Instance: OS Ubuntu 22.04 LTS (t3.small หรือ t3.medium)
  2. ตั้งค่า Inbound Security Group:
     - Port 22 (SSH) - เฉพาะ IP ส่วนตัว หรือ Any สำหรับ CI SSH
     - Port 80 (HTTP) - 0.0.0.0/0
     - Port 443 (HTTPS) - 0.0.0.0/0
  3. ติดตั้ง Docker Engine และ Docker Compose Plugin บน EC2
  4. สร้าง SSH Key Pair สำหรับ GitHub Actions
* **Acceptance Criteria:**
  - SSH เข้า EC2 ได้ และคำสั่ง `docker --version` รันผ่าน

---

### [BE-1] [Database] ออกแบบ Data Models ด้วย SQLAlchemy 2.0
* **ผู้รับผิดชอบ:** คนที่ 3 (Database Lead)
* **เป้าหมาย:** สร้างไฟล์โมเดลใน `app/models/` ให้ครบทุกความสัมพันธ์
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * โมเดลที่ต้องสร้าง:
    1. `User`: `id (UUID PK)`, `email (String Unique)`, `username (String Unique)`, `hashed_password (String)`, `full_name (String)`, `avatar_url (String)`, `is_active (Boolean)`, `created_at`
    2. `Workspace`: `id (UUID PK)`, `name (String)`, `slug (String Unique)`, `owner_id (UUID FK -> users.id)`
    3. `WorkspaceMember`: `workspace_id (UUID FK)`, `user_id (UUID FK)`, `role (String: OWNER/ADMIN/MEMBER)`
    4. `Channel`: `id (UUID PK)`, `workspace_id (UUID FK)`, `name (String)`, `is_private (Boolean)`
    5. `ChannelMember`: `channel_id (UUID FK)`, `user_id (UUID FK)`, `joined_at`
    6. `Message`: `id (UUID PK)`, `channel_id (UUID FK)`, `user_id (UUID FK)`, `content (Text)`, `parent_id (UUID FK -> messages.id Nullable)`, `created_at`
    7. `MessageRead`: `message_id (UUID FK)`, `user_id (UUID FK)`, `read_at (DateTime)`
* **Acceptance Criteria:**
  - ทุกโมเดลใช้ SQLAlchemy 2.0 Mapped type (`mapped_column`, `relationship`) แบบ Async

---

### [BE-2] [Database] ติดตั้ง Alembic และสร้าง Initial Migration
* **ผู้รับผิดชอบ:** คนที่ 3 (Database Lead)
* **สิ่งที่ต้องรอ:** BE-11 (Postgres พร้อม) และ BE-1 (Model พร้อม)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. ติดตั้ง Alembic: `alembic init -t async alembic`
  2. แก้ไข `alembic/env.py` ให้ดึง `Base.metadata` จาก `app.models`
  3. รัน `alembic revision --autogenerate -m "Initial livechat schema"`
  4. รัน `alembic upgrade head`
* **Acceptance Criteria:**
  - ตารางทั้งหมดถูกสร้างใน Postgres จริง และไม่มี Error

---

### [BE-3] & [BE-4] [Search Engine] Full-Text Search ด้วย PostgreSQL tsvector & ts_rank
* **ผู้รับผิดชอบ:** คนที่ 3 (Database Lead)
* **สิ่งที่ต้องรอ:** BE-2 (ตาราง messages มีอยู่จริง)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สร้าง Alembic Migration เพิ่มคอลัมน์ `search_vector`:
     ```sql
     ALTER TABLE messages ADD COLUMN search_vector tsvector;
     CREATE TRIGGER tsvectorupdate BEFORE INSERT OR UPDATE ON messages
     FOR EACH ROW EXECUTE FUNCTION tsvector_update_trigger(search_vector, 'pg_catalog.english', content);
     CREATE INDEX idx_messages_search_vector ON messages USING GIN(search_vector);
     ```
  2. เขียน Service `search_messages(db, channel_id, query, limit=30)`:
     - ใช้ SQLAlchemy ค้นหาผ่าน `search_vector.op("@@")(func.plainto_tsquery("english", query))`
     - จัดลำดับด้วย `func.ts_rank(search_vector, ...).desc()`
* **Acceptance Criteria:**
  - ส่งค้นหาคำ เช่น "meeting" แล้วระบบคืนรายการข้อความที่ตรงกันได้อย่างรวดเร็ว

---

### [BE-5] [Backend Core] โครงสร้าง FastAPI, Schemas และ CORS
* **ผู้รับผิดชอบ:** คนที่ 2 (Backend Lead)
* **เป้าหมาย:** วางรากฐาน API Server และอนุญาตให้ Frontend คุยได้
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สร้าง `app/main.py` พร้อม `CORSMiddleware`:
     ```python
     allow_origins=["*"] # หรือ http://localhost:5173 สำหรับ React Vite
     ```
  2. สร้างโฟลเดอร์ `app/schemas/` แบ่งเป็น `auth.py`, `workspace.py`, `channel.py`, `message.py`
  3. ติดตั้ง `prometheus-fastapi-instrumentator` เพื่อเปิดเส้นทาง `/metrics`
* **Acceptance Criteria:**
  - สั่ง `uvicorn app.main:app --reload` แล้วเปิดดู Swagger UI ที่ `http://localhost:8000/docs` ได้สำเร็จ

---

### [BE-6] [Auth API] Dual-Token JWT (/auth/login, /auth/refresh)
* **ผู้รับผิดชอบ:** คนที่ 2 (Backend Lead)
* **สิ่งที่ต้องรอ:** BE-2 (มีตาราง Users ใน DB)
* **รายละเอียด Contract ที่ต้องเขียนใน Issue:**
  * **POST `/api/v1/auth/register`**
    - Request Body: `{ "username": "alice", "email": "alice@test.com", "password": "Password123!", "full_name": "Alice Wonderland" }`
    - Response 201: `{ "id": "<uuid>", "username": "alice", "email": "alice@test.com" }`
  * **POST `/api/v1/auth/login`**
    - Request Body: `{ "username": "alice", "password": "Password123!" }`
    - Response 200:
      ```json
      {
        "access_token": "eyJhbGciOi...",
        "refresh_token": "eyJhbGciOi...",
        "token_type": "bearer",
        "user": { "id": "<uuid>", "username": "alice", "full_name": "Alice Wonderland" }
      }
      ```
  * **POST `/api/v1/auth/refresh`**
    - Request Body: `{ "refresh_token": "eyJhbGciOi..." }`
    - Response 200: `{ "access_token": "eyJhbGciOi...", "refresh_token": "eyJhbGciOi..." }`
* **Acceptance Criteria:**
  - สามารถ Register, Login ได้ Token และ Refresh Token ได้ใหม่เมื่อ Access Token หมดอายุ

---

### [BE-7] & [BE-8] [WebSocket Hub] Workspace WebSocket (/ws) & Redis Pub/Sub
* **ผู้รับผิดชอบ:** คนที่ 2 (Backend Lead)
* **สิ่งที่ต้องรอ:** BE-11 (Redis พร้อม) และ BE-6 (Token Auth พร้อม)
* **รายละเอียด WebSocket Protocol ที่ต้องเขียนใน Issue:**
  * **Endpoint:** `@app.websocket("/ws")` รับ Token ทาง Query param: `/ws?token=<access_token>`
  * **Client -> Server Frame Format (JSON):**
    ```json
    // ส่งข้อความ
    { "action": "send_message", "channel_id": "<uuid>", "content": "Hello team!" }

    // พิมพ์อยู่
    { "action": "typing", "channel_id": "<uuid>" }

    // อ่านข้อความแล้ว
    { "action": "read_receipt", "channel_id": "<uuid>", "message_id": "<uuid>" }

    // Heartbeat รักษาสถานะออนไลน์
    { "action": "heartbeat" }
    ```
  * **Server -> Client Broadcast Event Format (JSON):**
    ```json
    // ข้อความใหม่
    { "event": "new_message", "data": { "id": "<uuid>", "channel_id": "<uuid>", "user_id": "<uuid>", "username": "alice", "content": "Hello team!", "created_at": "2026-10-17T..." } }

    // แจ้งเตือนกำลังพิมพ์
    { "event": "user_typing", "data": { "channel_id": "<uuid>", "user_id": "<uuid>", "username": "alice" } }

    // อัปเดตสถานะออนไลน์
    { "event": "presence_update", "data": { "user_id": "<uuid>", "status": "online" } }
    ```
  * **Redis Pub/Sub:** Backend รับข้อความแล้ว Publish เข้า Redis Channel `pubsub:channel:{channel_id}` เพื่อกระจายให้ทุก Client
* **Acceptance Criteria:**
  - Client เชื่อมต่อครั้งเดียว สลับคุยได้หลาย Channel และได้รับข้อความแบบเรียลไทม์

---

### [BE-9] [Presence] ระบบ Heartbeat สถานะ Online/Offline (TTL 60s)
* **ผู้รับผิดชอบ:** คนที่ 2 (Backend Lead)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. เมื่อ Client ต่อ WS หรือส่ง `{ "action": "heartbeat" }` ให้สั่ง Redis:
     `SET presence:user:{user_id} "online" EX 60`
  2. ดึงรายชื่อ User ออนไลน์: ตรวจสอบ Key `presence:user:*`
* **Acceptance Criteria:**
  - เมื่อปิดแท็บเบราว์เซอร์ครบ 60 วินาที คีย์หมดอายุ และสถานะเปลี่ยนเป็น Offline อัตโนมัติ

---

### [BE-10] [DevOps] สร้าง Dockerfile ของ Backend
* **ผู้รับผิดชอบ:** คนที่ 4 (DevOps Lead - ตัวคุณเอง)
* **เป้าหมาย:** แพ็ก Backend ให้พร้อมรันใน Docker
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

### [BE-13] & [BE-14] [CI/CD & Cloud] GitHub Actions Deploy สู่ AWS EC2 & SSL
* **ผู้รับผิดชอบ:** คนที่ 4 (DevOps Lead - ตัวคุณเอง)
* **เป้าหมาย:** เชื่อมต่อ GitHub เข้ากับ AWS EC2 เพื่อ Auto-deploy
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * สร้าง `.github/workflows/deploy.yml`:
    1. รัน Pytest (พร้อม Service Container Postgres/Redis)
    2. SSH ไปที่ AWS EC2 ผ่าน Secrets `AWS_SSH_PRIVATE_KEY`, `AWS_HOST`
    3. รันสคริปต์บนเซิร์ฟเวอร์:
       ```bash
       cd /opt/livechat-backend
       git pull origin main
       docker compose -f docker-compose.prod.yml up -d --build
       docker compose exec -T backend alembic upgrade head
       ```
    4. ติดตั้ง Certbot Nginx สำหรับ HTTPS
* **Acceptance Criteria:**
  - เมื่อ Merge PR เข้า `main` เซิร์ฟเวอร์บน AWS จะอัปเดตโค้ดล่าสุดอัตโนมัติ

---

# 📦 REPO 2: `livechat-frontend`

---

### [FE-1] [Setup] ติดตั้ง React + Vite + TypeScript + Tailwind CSS
* **ผู้รับผิดชอบ:** คนที่ 1 (Frontend Lead)
* **เป้าหมาย:** สร้างโครงโปรเจกต์หน้าบ้าน
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สั่งรัน: `npm create vite@latest livechat-frontend -- --template react-ts`
  2. ติดตั้ง Tailwind CSS และ Lucide Icons:
     `npm install -D tailwindcss postcss autoprefixer && npx tailwindcss init -p`
     `npm install lucide-react axios react-router-dom`
  3. ตั้งค่าโฟลเดอร์: `src/components/`, `src/contexts/`, `src/services/`, `src/pages/`
* **Acceptance Criteria:**
  - สั่ง `npm run dev` แล้วเปิด `http://localhost:5173` ติดหน้าจอ Tailwind CSS สวยงาม

---

### [FE-2] [Auth UI] หน้าจอ Login / Register & Axios Interceptor
* **ผู้รับผิดชอบ:** คนที่ 1 (Frontend Lead)
* **สิ่งที่ต้องรอ:** BE-6 (Auth API เสร็จ)
* **รายละเอียด Contract ที่ต้องเขียนใน Issue:**
  1. สร้าง `src/services/api.ts` ใช้ Axios:
     ```typescript
     const api = axios.create({ baseURL: "http://localhost:8000/api/v1" });
     ```
  2. ทำ **Axios Interceptor** ดัก HTTP 401:
     - หาก Token หมดอายุ ให้เรียก `POST /auth/refresh` ส่ง `refresh_token` ไปขอ Access Token ใหม่
     - นำ Token ใหม่ไปยิงคำขอเดิมซ้ำ (Seamless Auto-Refresh)
  3. ออกแบบหน้า UI Login/Register สวยหรูสไตล์ Slack/Discord พร้อมเก็บ Token ใน `localStorage`
* **Acceptance Criteria:**
  - สามารถล็อกอิน และระบบไม่หลุดเมื่อ Access Token หมดอายุ

---

### [FE-3] & [FE-4] [Chat UI] Sidebar, Channel List และ ChatArea
* **ผู้รับผิดชอบ:** คนที่ 1 (Frontend Lead)
* **เป้าหมาย:** ออกแบบ Layout หลักของระบบแชท
* **รายละเอียดที่ต้องเขียนใน Issue:**
  * Components ที่ต้องสร้าง:
    1. `Sidebar.tsx`: รายชื่อ Workspaces และ Channels มีปุ่มบวกสร้างห้องใหม่
    2. `ChatArea.tsx`: หัวห้องแชท, รายการข้อความที่ Scroll ขึ้นเพื่อโหลดข้อความเก่าได้
    3. `MessageItem.tsx`: Avatar, ชื่อผู้ส่ง, เวลา, เนื้อหาข้อความ และสัญลักษณ์ Read by
    4. `MessageInput.tsx`: ช่องพิมพ์ข้อความ, ปุ่มส่ง, และตรวจจับการกดแป้นพิมพ์ส่ง Event Typing
* **Acceptance Criteria:**
  - UI ตอบสนองได้ลื่นไหล รองรับ Responsive Design ทั้งจอคอมและมือถือ

---

### [FE-5] [WebSocket Client] เชื่อมต่อ WebSocketContext และ Real-time Events
* **ผู้รับผิดชอบ:** คนที่ 1 (Frontend Lead)
* **สิ่งที่ต้องรอ:** BE-7 (WebSocket Hub เสร็จ)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. สร้าง `src/contexts/WebSocketContext.tsx`:
     - เชื่อมต่อ `ws://localhost:8000/ws?token=${accessToken}`
     - มีฟังก์ชัน `sendMessage(channelId, text)`, `sendTyping(channelId)`
     - จัดการ Auto-reconnect หากสัญญาณหลุด
  2. ฟัง Event จาก Server:
     - เมื่อได้รับ `new_message` ➡️ เพิ่มข้อความเข้า State ทันทีโดยไม่ต้อง Refresh หน้า
     - เมื่อได้รับ `user_typing` ➡️ แสดงข้อความ *"Alice is typing..."* เป็นเวลา 3 วินาที
     - ส่ง Heartbeat `{ "action": "heartbeat" }` ทุกๆ 30 วินาที
* **Acceptance Criteria:**
  - เปิดเบราว์เซอร์ 2 หน้าต่าง ล็อกอินคนละชื่อ พิมพ์ข้อความแล้วเด้งหากันแบบเรียลไทม์

---

### [FE-6] [Search UI] ค้นหาข้อความย้อนหลัง (Full-Text Search Modal)
* **ผู้รับผิดชอบ:** คนที่ 1 (Frontend Lead)
* **สิ่งที่ต้องรอ:** BE-3 & BE-4 (Search API เสร็จ)
* **รายละเอียดที่ต้องเขียนใน Issue:**
  1. ทำช่องค้นหาด้านบน หรือกดคีย์ลัด `Ctrl + K` เปิด Search Modal
  2. ยิง API: `GET /api/v1/channels/{channel_id}/search?q={query}`
  3. แสดงผลลัพธ์ข้อความที่พบ ไฮไลต์คำที่ค้นหา และคลิกเพื่อเด้งไปยังตำแหน่งข้อความนั้นได้
* **Acceptance Criteria:**
  - ค้นหาคำได้รวดเร็ว แสดงผลลัพธ์พร้อมชื่อคนส่งและวันที่อย่างถูกต้อง

---

### [FE-7] [DevOps] Dockerfile Multi-Stage สำหรับ Frontend
* **ผู้รับผิดชอบ:** คนที่ 4 (DevOps Lead - ตัวคุณเอง)
* **เป้าหมาย:** บิลด์ React เป็นไฟล์ Static แล้วเสิร์ฟด้วย Nginx
* **รายละเอียดที่ต้องเขียนใน Issue:**
  ```dockerfile
  # Build Stage
  FROM node:20-alpine AS builder
  WORKDIR /app
  COPY package*.json ./
  RUN npm install
  COPY . .
  RUN npm run build

  # Production Stage
  FROM nginx:alpine
  COPY --from=builder /app/dist /usr/share/nginx/html
  COPY nginx.conf /etc/nginx/conf.d/default.conf
  EXPOSE 80
  CMD ["nginx", "-g", "daemon off;"]
  ```
* **Acceptance Criteria:**
  - รัน Container หน้าเว็บแล้วเปิดผ่านพอร์ต 80 ได้ทันที
