# livechat-backend

## AWS EC2 — Backend #3

ไฟล์ Terraform และ bootstrap สำหรับ Ubuntu 22.04, Security Group, SSH key pair และ Docker/Compose
อยู่ที่ [infra/ec2/README.md](infra/ec2/README.md)
ยังไม่ได้ provision เครื่องจริง เนื่องจาก AWS Organizations SCP ปฏิเสธ EC2 API ของบัญชีที่มีอยู่

## Local infrastructure — Backend #2

ต้องติดตั้ง Docker Engine/Docker Desktop พร้อม Docker Compose และเปิด Engine ก่อนใช้งาน
รันคำสั่งทั้งหมดจากโฟลเดอร์ backend repository

```powershell
Copy-Item .env.example .env
docker compose config --quiet
docker compose up -d --wait
docker compose ps
```

บน macOS/Linux ใช้ `cp .env.example .env` แทน `Copy-Item`
ค่าเริ่มต้นรันเฉพาะ **Postgres 15 และ Redis 7** เพื่อให้ทีมเริ่มพัฒนาได้ทันที
โดยยังไม่ต้องมีโค้ดหรือ Dockerfile ของ API/Frontend

| บริการ | URL เมื่อรันแอปจากเครื่อง |
|---|---|
| PostgreSQL (SQLAlchemy async) | `postgresql+asyncpg://postgres:postgres@localhost:5432/livechat_db` |
| Redis | `redis://localhost:6379/0` |

`.env.example` ระบุเฉพาะชื่อตัวแปรโดยเว้นค่าว่าง ให้ใส่ค่าของเครื่องคุณใน `.env`
ตัวแปรที่เว้นว่างจะใช้ค่า local development เริ่มต้นใน Compose; ใส่ค่าจริงก่อนนำขึ้น server
พอร์ต DB/Redis และ API ผูกกับ `127.0.0.1`; เปลี่ยน host ports ได้ใน `.env` หากพอร์ตชน
ถ้าเปลี่ยนชื่อผู้ใช้/รหัสผ่าน ต้องปรับ URL ของแอปที่รันบนเครื่องตามด้วย
Compose นี้ประกอบ DATABASE_URL จากค่าดังกล่าวโดยตรง จึงใช้ชื่อผู้ใช้/รหัสผ่านที่เป็น URL-safe

ตรวจบริการ:

```powershell
docker compose exec postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose exec redis redis-cli ping
```

Redis ต้องตอบ `PONG`; Postgres ต้องแสดง `accepting connections`

## Full application profile

Compose เตรียมบริการครบ Nginx, Postgres, Redis, API และ Frontend ไว้ในไฟล์เดียว
โดยใช้ profile `app` สำหรับบริการที่ยังรอทีมพัฒนา:

- **Backend #1 และ #10:** backend มี `Dockerfile`, dependencies และ FastAPI ที่ฟังพอร์ต 8000
- **Frontend #1 และ #2:** frontend มีโครงแอปและ `Dockerfile` ที่เสิร์ฟเว็บบนพอร์ต 80
- ตั้ง `FRONTEND_CONTEXT` ใน `.env` ให้ชี้ไป repo frontend; ค่าเริ่มต้นคือ `../livechat frontend`
- Backend ต้องอ่าน `DATABASE_URL` และ `REDIS_URL` จาก environment และตั้งค่าอื่นของแอปตามที่ BE #10/#11 กำหนด
- Frontend เรียก API ผ่าน `/api/v1` และ WebSocket ผ่าน host เดียวกันที่ `/ws` เมื่อใช้ Nginx

เมื่อ prerequisites พร้อม:

```powershell
docker compose --profile app config --quiet
docker compose --profile app up -d --build
docker compose --profile app ps
```

| เส้นทาง | ปลายทาง |
|---|---|
| `http://localhost/` | Frontend |
| `http://localhost/api/v1/…` | Backend โดยคง path เดิม |
| `ws://localhost/ws?token=…` | Backend พร้อม WebSocket upgrade |
| `http://localhost:8000/docs` | Backend โดยตรงสำหรับ local development |

API ใน container เชื่อม DB ที่ `postgres:5432` และ Redis ที่ `redis:6379` แทน `localhost`
Compose รอให้ DB/Redis healthy ก่อนเริ่ม API แต่ยังต้องรอแอปพร้อมและทำ migration ตาม BE #7
Nginx รับ HTTP ใน issue นี้; HTTPS/SSL อยู่ใน Backend #5

## หยุดบริการและเก็บข้อมูล

```powershell
docker compose --profile app logs --tail=100
docker compose --profile app down
```

Named volumes เก็บข้อมูล Postgres และ Redis หลังหยุด/สร้าง container ใหม่
Redis เปิด AOF เพื่อบันทึกข้อมูล การเปลี่ยน `POSTGRES_USER`, `POSTGRES_PASSWORD` หรือ `POSTGRES_DB`
ใน `.env` ไม่แก้ฐานข้อมูลที่ initialize ไว้แล้ว ต้องเปลี่ยนผ่าน SQL หรือใช้ volume ใหม่สำหรับข้อมูลทดสอบ
คำสั่ง `docker compose --profile app down -v` จะลบข้อมูลทั้งหมด ใช้เฉพาะเมื่อตั้งใจ reset local database
