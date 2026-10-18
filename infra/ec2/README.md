# AWS EC2 — Backend #3

Terraform สำหรับ Ubuntu 22.04 LTS (`t3.small` หรือ `t3.medium`), SSH key pair,
Security Group พอร์ต 80/443 และ SSH 22 เฉพาะ public IP ที่กำหนด
cloud-init ติดตั้ง Docker Engine/Compose Plugin จาก Docker apt repository
พร้อมโฟลเดอร์ `/opt/livechat-backend` และ `/opt/livechat-frontend`

## สถานะการตรวจสอบ

วันที่ 18 ตุลาคม 2026 AWS profile ที่มีอยู่เรียก STS ได้ แต่ `ec2:DescribeVpcs`
ถูกปฏิเสธด้วย **explicit deny ใน Service Control Policy (SCP)**
จึงยังไม่ได้สร้าง EC2, Security Group หรือ import key pair บนบัญชีจริง
ต้องให้ผู้ดูแล AWS Organizations ตรวจและอนุญาต EC2 ใน region ที่จะใช้ก่อน
การเพิ่ม IAM Allow อย่างเดียวไม่สามารถลบผลของ SCP Deny ได้

ไฟล์นี้เป็นวิธี provision และตรวจรับงาน ไม่ใช่หลักฐานว่าเครื่องพร้อมใช้งานแล้ว
ตรวจผ่านแล้ว: Terraform format/validate, mock tests 3 กรณี (server plan,
ปฏิเสธ SSH ที่เปิดทั่วโลก, ปฏิเสธ subnet คนละ VPC) และ Linux shell syntax ของ cloud-init
ไฟล์ public key ใน `tests/fixtures` ใช้เฉพาะ mock tests และไม่มี private key เก็บอยู่ใน repository

## เตรียมค่าจริงในเครื่อง

ต้องมี Terraform >= 1.7, AWS CLI, OpenSSH และสิทธิ์ EC2 ที่องค์กรอนุญาต
module ใช้ VPC/public subnet เดิม ไม่สร้าง network หรือเปลี่ยน route table ให้
subnet ต้องมีเส้นทางออก internet ผ่าน Internet Gateway เพื่อให้ SSH และติดตั้ง packages ได้

จาก repo root สร้าง key เฉพาะงาน deploy โดยเก็บ private key ใน `.local` ที่ถูก gitignore:

```powershell
New-Item -ItemType Directory -Force .local
ssh-keygen -t ed25519 -C livechat-deploy -f .local/livechat-deploy
```

ตั้ง passphrase ตามวิธีใช้ key ของทีม หากใช้ passphrase ใน GitHub Actions ต้องส่ง passphrase
ผ่าน GitHub Secret เพิ่มใน BE #4 ห้ามใส่ private key หรือ passphrase ใน repository/Terraform variables
Terraform อ่านเฉพาะไฟล์ `.pub` และ import public key เป็น EC2 Key Pair

```powershell
Copy-Item infra/ec2/terraform.tfvars.example infra/ec2/terraform.tfvars
```

เติมค่าใน `terraform.tfvars` ซึ่งถูก gitignore:

| ตัวแปร | ค่าที่ต้องใส่ |
|---|---|
| `aws_region` | region ที่องค์กรอนุญาต |
| `vpc_id` | VPC เดิมของโปรเจกต์ |
| `subnet_id` | public subnet ใน VPC นั้น |
| `ssh_allowed_cidrs` | public IPv4 ของเครื่องหรือ runner ที่อนุญาตในรูป `/32` |
| `ssh_public_key_path` | absolute path ของ `.local/livechat-deploy.pub` (บน Windows ใช้ `/`) |

ตัวเลือก `instance_type` เริ่มที่ `t3.small`, `root_volume_gb` เริ่มที่ 30 GiB encrypted gp3
ไม่สร้าง IAM access keys และไม่เก็บ AWS credentials ลงไฟล์โครงการ
ชื่อ resources ใช้ prefix `livechat`; เปลี่ยน `project_name` หากมีชุดเดิมอยู่แล้ว

## ตรวจและ provision

```powershell
aws sts get-caller-identity
terraform -chdir=infra/ec2 init
terraform -chdir=infra/ec2 fmt -check
terraform -chdir=infra/ec2 validate
terraform -chdir=infra/ec2 test
terraform -chdir=infra/ec2 plan -out=ec2.tfplan
terraform -chdir=infra/ec2 apply ec2.tfplan
terraform -chdir=infra/ec2 output
```

`apply` สร้างทรัพยากรที่มีค่าใช้จ่ายจริง ให้ตรวจ region/resources ใน saved plan ก่อนรัน
เก็บ state/plan เฉพาะเครื่องที่ดูแล infrastructure; ต้องเก็บ state ให้ปลอดภัยเพื่อจัดการชุดเดิมต่อ
หากทำร่วมกันหลายคนให้ย้ายไป shared backend พร้อม locking ก่อน apply พร้อมกัน

## ตรวจรับหลังสร้างเครื่องจริง

1. ใช้ `ssh_command` จาก Terraform output เชื่อมต่อด้วย private key ที่คู่กับ public key
2. ตรวจ SSH host key fingerprint กับ instance console output ก่อนยืนยัน host ครั้งแรก
3. รอ bootstrap และตรวจ Docker:

```bash
sudo cloud-init status --wait
sudo test -f /var/lib/livechat-bootstrap-complete
docker --version
docker compose version
docker info
ls -ld /opt/livechat-backend /opt/livechat-frontend
```

หากติดตั้งไม่ผ่าน ตรวจ `sudo tail -n 100 /var/log/cloud-init-output.log`
HTTP/HTTPS จะยังไม่มีแอปตอบจนกว่าจะ deploy Compose ใน BE #4 และตั้ง TLS ใน BE #5
การเปลี่ยน cloud-init/AMI อาจทำให้ Terraform replace เครื่อง ต้องสำรองข้อมูลก่อน apply การเปลี่ยนดังกล่าว
public IP อาจเปลี่ยนหลัง stop/start; ให้อัปเดต host/DNS ตาม output ล่าสุด

สำหรับ BE #4 เก็บ `AWS_EC2_HOST`, `AWS_EC2_USER` และ `AWS_SSH_PRIVATE_KEY`
เป็น GitHub environment/repository secrets; ไม่ commit ค่าจริง
runner ที่ใช้ SSH ต้องมี IP ตรงกับ allowlist นี้ เช่น self-hosted runner ที่มี public IP คงที่
ห้ามแก้ allowlist เป็น `0.0.0.0/0` เพื่อรองรับ runner

หลักฐานปิด issue: instance ID, Security Group rules, SSH สำเร็จ และผล Docker/Compose จริง
ห้ามปิด BE #3 จากผล Terraform mock tests อย่างเดียว

## เอกสารอ้างอิง

- [Docker Engine บน Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [ค้นหา Ubuntu AMI ของ Canonical](https://ubuntu.com/aws/docs/aws-how-to/instances/find-ubuntu-images/)
- [Terraform AWS provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
