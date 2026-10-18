output "instance_id" {
  description = "EC2 instance managed by this module."
  value       = aws_instance.app.id
}

output "public_ip" {
  description = "Public IPv4 address; may change after stop/start (no Elastic IP)."
  value       = aws_instance.app.public_ip
}

output "security_group_id" {
  description = "Security group allowing only HTTP, HTTPS and approved SSH sources."
  value       = aws_security_group.web.id
}

output "ssh_user" {
  value = "ubuntu"
}

output "ssh_command" {
  value = "ssh -i \"${trimsuffix(pathexpand(var.ssh_public_key_path), ".pub")}\" ubuntu@${aws_instance.app.public_ip}"
}
