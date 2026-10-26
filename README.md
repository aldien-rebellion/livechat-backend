# Real-Time Live Chat Platform — Backend Service

ระบบ Backend ของแพลตฟอร์มแชทเรียลไทม์ (Real-Time Live Chat Platform) พัฒนาด้วย **FastAPI (Python 3.11)**, **PostgreSQL 15** และ **Redis 7** ออกแบบสถาปัตยกรรมแบบ Layered Architecture พร้อมรองรับการขยายตัว (Scalability), ความปลอดภัยระดับ Production (RBAC, Non-root User, Dual-Token JWT) และระบบสังเกตการณ์ (Observability) ครบวงจร

---

## สารบัญ
1. [ภาพรวมสถาปัตยกรรมระบบ (Architecture Overview)](#1-ภาพรวมสถาปัตยกรรมระบบ-architecture-overview)
2. [เทคโนโลยีและเครื่องมือที่ใช้ (Tech Stack)](#2-เทคโนโลยีและเครื่องมือที่ใช้-tech-stack)
3. [การเริ่มต้นใช้งานบนเครื่อง Local (Local Development)](#3-การเริ่มต้นใช้งานบนเครื่อง-local-local-development)
4. [การจัดการฐานข้อมูลและ Migrations (Alembic)](#4-การจัดการฐานข้อมูลและ-migrations-alembic)
5. [ระบบจัดการสิทธิ์ผู้ดูแลระบบ (Admin RBAC & Operator CLI)](#5-ระบบจัดการสิทธิ์ผู้ดูแลระบบ-admin-rbac--operator-cli)
6. [ระบบค้นหาข้อความขั้นสูง (PostgreSQL Full-Text Search)](#6-ระบบค้นหาข้อความขั้นสูง-postgresql-full-text-search)
7. [ระบบโครงสร้างพื้นฐานบนคลาวด์ (Infrastructure as Code - Terraform)](#7-ระบบโครงสร้างพื้นฐานบนคลาวด์-infrastructure-as-code---terraform)
8. [ระบบสังเกตการณ์และการตรวจวัด (Observability & Monitoring)](#8-ระบบสังเกตการณ์และการตรวจวัด-observability--monitoring)
9. [ระบบ CI/CD Pipeline (Automated Quality & Deployment)](#9-ระบบ-cicd-pipeline-automated-quality--deployment)
10. [คำสั่งที่ใช้บ่อย (Operations Cheat Sheet)](#10-คำสั่งที่ใช้บ่อย-operations-cheat-sheet)

---

## 1. ภาพรวมสถาปัตยกรรมระบบ (Architecture Overview)

ระบบทำงานร่วมกันในรูปแบบ Multi-Container Microservices โดยมี **Nginx** ทำหน้าที่เป็น Ingress Reverse Proxy รับคำขอจากผู้ใช้แล้วกระจายไปยังบริการภายใน:

```
[ Client Browser / SPA ]
          │  HTTPS (443) / WSS
          ▼
   ┌──────────────┐
   │    Nginx     │ ──► Static Files SPA (Frontend)
   │Reverse Proxy │ ──► REST API /api/v1/* (FastAPI)
   └──────┬───────┘ ──► WebSocket /ws (FastAPI TCP Tunnel)
          │
          ├──► [ FastAPI Backend ] (:8000)
          │           │
          │           ├──► [ PostgreSQL 15 ] (:5432) ── Relational Data, tsvector, GIN Index
          │           └──► [ Redis 7 ] (:6379) ──────── Pub/Sub Message Broker, Presence TTL
          │
          └──► [ Prometheus ] (:9090) ── Scrape /metrics
                      │
                      ▼
               [ Grafana ] (:3000) ── Dashboard as Code (RPS, Latency p95, WS Connections)
```

---

## 2. เทคโนโลยีและเครื่องมือที่ใช้ (Tech Stack)

| ส่วนประกอบ | เครื่องมือ/เทคโนโลยี | รายละเอียดและหน้าที่ |
|---|---|---|
| **API Framework** | FastAPI (Python 3.11) | Asynchronous REST API และ WebSocket Server |
| **Relational Database** | PostgreSQL 15 | จัดเก็บ Users, Workspaces, Channels, Messages พร้อม `tsvector` FTS |
| **In-Memory Cache & Broker** | Redis 7 Alpine | จัดการ WebSocket Pub/Sub Broadcast และ Online Presence (TTL 60s) |
| **Database Migrations** | Alembic + SQLAlchemy 2.0 | Version Control สำหรับโครงสร้างตารางฐานข้อมูลแบบ Async |
| **Reverse Proxy & Gateway** | Nginx Alpine | SSL Termination, Routing (`/api/v1/`, `/ws`, `/grafana/`), Static Cache |
| **Containerization** | Docker & Docker Compose v2 | ควบคุม Multi-Container Isolation และ Healthchecks |
| **Infrastructure as Code** | Terraform (AWS Provider) | จัดเตรียม EC2 (Ubuntu 22.04), Security Groups และ SSH Keys |
| **Observability** | Prometheus + Grafana | ดึงตัวชี้วัด `/metrics` และแสดงผล Dashboard Real-time |
| **CI/CD Automation** | GitHub Actions | Automated Linting, Testing ด้วย Service Containers และ SSH Deploy |

---

## 3. การเริ่มต้นใช้งานบนเครื่อง Local (Local Development)

### 3.1 ข้อกำหนดเบื้องต้น (Prerequisites)
* ติดตั้ง [Docker Desktop](https://www.docker.com/products/docker-desktop/) (หรือ Docker Engine + Compose v2)
* Python 3.11+ (สำหรับรันสคริปต์หรือทดสอบนอกคอนเทนเนอร์)
* Git

### 3.2 การรันระบบเต็มรูปแบบ (Full Application Stack)
Compose รันครบทุกบริการทั้ง Nginx, FastAPI Backend, React Frontend, PostgreSQL, Redis, Prometheus และ Grafana ด้วย Profile `app`:

```powershell
# 1. เข้าโฟลเดอร์ livechat backend
cd "livechat backend"

# 2. คัดลอกไฟล์ Environment Variables
Copy-Item .env.example .env

# 3. สั่ง Build และรันคอนเทนเนอร์ทั้งหมด
docker compose --profile app up -d --build

# 4. ตรวจสอบสถานะการทำงาน (ต้องขึ้น Healthy ทั้งหมด)
docker compose ps
```

### 3.3 Endpoint สำคัญเมื่อรันบนเครื่อง Local
* **หน้าเว็บแชทหลัก (Frontend):** `http://localhost/`
* **API Documentation (Swagger UI):** `http://localhost:8000/docs`
* **Healthcheck Endpoint:** `http://localhost:8000/healthcheck`
* **Metrics Raw Data:** `http://localhost:8000/metrics`
* **Grafana Monitoring Dashboard:** `http://localhost:3000/` *(User: `admin` / Password: `admin1234`)*

---

## 4. การจัดการฐานข้อมูลและ Migrations (Alembic)

ระบบใช้ **Alembic** จัดการโครงสร้างฐานข้อมูลแบบอัตโนมัติ เพื่อป้องกันการสูญหายของข้อมูลเมื่อมีการอัปเดตสคีมา:

```powershell
# รัน Migration ให้เป็นเวอร์ชันล่าสุด (Head)
docker compose exec backend alembic upgrade head

# ตรวจสอบประวัติ Revision ปัจจุบันของฐานข้อมูล
docker compose exec backend alembic current

# สร้าง Migration Script ใหม่หลังแก้ไข Models
docker compose exec backend alembic revision --autogenerate -m "describe_changes"
```

---

## 5. ระบบจัดการสิทธิ์ผู้ดูแลระบบ (Admin RBAC & Operator CLI)

ระบบใช้หลักการ **Role-Based Access Control (RBAC)** โดยผู้ใช้ที่สมัครเข้ามาใหม่ทุกคนจะเริ่มต้นด้วยสิทธิ์ธรรมดา (`is_admin=false`) การแต่งตั้งหรือปลดสิทธิ์ระดับ Global Admin จะต้องกระทำผ่านเครื่องมือ Operator CLI เท่านั้น:

### ตารางสิทธิ์ของผู้ใช้ (Permission Matrix)
| ฟังก์ชันการทำงาน | Global Admin | Workspace Owner | Normal Member |
|---|:---:|:---:|:---:|
| สร้าง Workspace ใหม่ | ✅ ได้ | ❌ ไม่ได้ | ❌ ไม่ได้ |
| สร้าง Channel ภายใน Workspace | ✅ ได้ | ✅ ได้ | ✅ ได้ |
| ลบ Workspace และข้อความทั้งหมด | ✅ ได้ | ✅ เฉพาะที่เป็นเจ้าของ | ❌ ไม่ได้ |
| ลบ Channel และข้อความทั้งหมด | ✅ ได้ | ✅ เฉพาะที่เป็นเจ้าของ | ❌ ไม่ได้ |

### การให้และยกเลิกสิทธิ์ Admin ด้วย CLI
รันคำสั่งผ่านคอนเทนเนอร์ backend:

```bash
# ให้สิทธิ์ Global Admin แก่ผู้ใช้ (--grant)
docker compose exec backend python -m scripts.set_admin user@example.com --grant

# ปลดสิทธิ์ Global Admin กลับเป็นผู้ใช้ทั่วไป (--revoke)
docker compose exec backend python -m scripts.set_admin user@example.com --revoke
```

### กลไกความปลอดภัยในการลบข้อมูล (Safe Deletion & Tombstones)
* การลบห้องแชทหรือ Workspace จะต้องผ่านหน้าต่าง **ConfirmDeleteDialog** บน UI โดยผู้ใช้ต้องพิมพ์ชื่อห้องตรงกัน 100%
* เมื่อถูกลบ ข้อมูลข้อความจะถูกล้าง และระบบจะสร้าง **Deletion Tombstones** ไว้ เพื่อป้องกันไม่ให้ไคลเอนต์เก่าหรือ WebSocket Reconnect กู้คืนห้องที่ถูกลบไปแล้วกลับมาได้

---

## 6. ระบบค้นหาข้อความขั้นสูง (PostgreSQL Full-Text Search)

ระบบค้นหาข้อความย้อนหลังออกแบบให้ทำงานรวดเร็วระดับ Sub-second บนฐานข้อมูล PostgreSQL:
* **`tsvector`:** ข้อความทุกข้อความจะถูกทำ Tokenize และสร้าง Index อัตโนมัติในตอนบันทึกลงตาราง `messages`
* **GIN Index (Generalized Inverted Index):** ดัชนีช่วยค้นหาคำศัพท์ได้อย่างแม่นยำ ไม่ต้องทำการ Full Table Scan (`LIKE %...%`)
* **`ts_rank`:** คำนวณคะแนนความเกี่ยวข้องเพื่อจัดอันดับข้อความที่ตรงกับคีย์เวิร์ดมากที่สุดส่งกลับไปยัง UI (เรียกใช้ผ่านคีย์ลัด `Ctrl + K`)

---

## 7. ระบบโครงสร้างพื้นฐานบนคลาวด์ (Infrastructure as Code - Terraform)

ไฟล์โครงสร้างระบบคลาวด์สำหรับสร้างและควบคุม **AWS EC2 (Ubuntu 22.04 LTS)** จัดเก็บอยู่ที่ `infra/ec2/`

### 7.1 การตั้งค่าตัวแปร (`terraform.tfvars`)
```hcl
aws_region          = "ap-southeast-2"
vpc_id              = "vpc-xxxxxxxxxxxxxxxxx"
subnet_id           = "subnet-xxxxxxxxxxxxxxxxx"
ssh_allowed_cidrs   = ["xxx.xxx.xxx.xxx/32"]
ssh_public_key_path = "D:/project livechat/livechat backend/.local/livechat-deploy.pub"
instance_type       = "t3.small"
```

### 7.2 คำสั่งจัดการวงจรชีวิต Infrastructure (Lifecycle)
```powershell
cd infra/ec2

# ตรวจสอบความถูกต้องและสร้างแผน
terraform init
terraform validate
terraform plan -out=ec2.tfplan

# สั่งสร้างเครื่องและระบบความปลอดภัย (Provision)
terraform apply ec2.tfplan

# ทำลายทรัพยากรทั้งหมดเมื่อเสร็จสิ้นโครงการ (Decommission & 0 Cost)
terraform destroy -auto-approve
```

---

## 8. ระบบสังเกตการณ์และการตรวจวัด (Observability & Monitoring)

ระบบติดตั้งระบบวัดประสิทธิภาพและการแจ้งเตือนตามมาตรฐาน Site Reliability Engineering (SRE):
* **Prometheus (Scraper):** ดึงค่าจาก `/metrics` ของ FastAPI ทุก 5-15 วินาที
* **Grafana (Dashboard as Code):** คอนฟิก Datasource และ Dashboard อัตโนมัติผ่านไฟล์ JSON ใน `grafana/provisioning/`
* **ตัวชี้วัดสำคัญ (Key Metrics):**
  * `http_requests_total` (Requests Per Second - RPS)
  * `http_request_duration_seconds` (Latency Percentiles: p50, p95, p99)
  * `active_websocket_connections` (จำนวนผู้ใช้ที่เปิดการเชื่อมต่อแชทสด)

---

## 9. ระบบ CI/CD Pipeline (Automated Quality & Deployment)

การทำงานแบบอัตโนมัติผ่าน **GitHub Actions** (`.github/workflows/`):

1. **Continuous Integration (CI):**
   * ตรวจสอบโค้ดและ Syntax ด้วย `flake8`
   * รัน Automated Unit & Integration Tests ด้วย `pytest`
   * จำลอง Service Containers ของจริง (PostgreSQL 15 และ Redis 7) พร้อม Healthcheck ใน Runner
2. **Continuous Deployment (CD):**
   * สร้าง Multi-stage Docker Image และ Push ขึ้น **Docker Hub**
   * เชื่อมต่อผ่าน SSH เข้า AWS EC2 แบบอัตโนมัติ
   * สั่ง `docker compose pull` และ `docker compose up -d` แบบ Zero-Downtime
   * สั่งรัน `alembic upgrade head` เพื่ออัปเดตสคีมาฐานข้อมูลอัตโนมัติ

---

## 10. คำสั่งที่ใช้บ่อย (Operations Cheat Sheet)

```bash
# ตรวจสอบสถานะและพอร์ตของคอนเทนเนอร์ทั้งหมด
docker compose ps

# ดูบันทึกการทำงาน (Logs) สดแบบ Real-time
docker compose logs -f backend
docker compose logs -f nginx

# ตรวจสอบสุขภาพของ Redis
docker compose exec redis redis-cli ping
docker compose exec redis redis-cli keys "presence:*"

# ตรวจสอบสุขภาพของ PostgreSQL
docker compose exec postgres pg_isready -U postgres -d livechat_db

# ตรวจสอบการใช้ทรัพยากร CPU และ RAM
docker stats --no-stream

# ปิดระบบและลบคอนเทนเนอร์ (คงข้อมูลใน Volumes ไว้)
docker compose --profile app down

# ปิดระบบและล้างข้อมูลทั้งหมด (Reset ข้อมูลทดสอบ)
docker compose --profile app down -v
```
