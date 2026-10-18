variable "aws_region" {
  description = "AWS region permitted by the account's organization policies."
  type        = string

  validation {
    condition     = can(regex("^[a-z]{2}(-[a-z]+)+-[0-9]+$", var.aws_region))
    error_message = "Set a valid AWS region explicitly."
  }
}

variable "project_name" {
  description = "Name prefix for this project's EC2 resources."
  type        = string
  default     = "livechat"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,31}$", var.project_name))
    error_message = "Use 3-32 lowercase letters, numbers or hyphens, starting with a letter."
  }
}

variable "vpc_id" {
  description = "Existing VPC; this module does not create or modify network routing."
  type        = string

  validation {
    condition     = can(regex("^vpc-[0-9a-f]+$", var.vpc_id))
    error_message = "Set an existing VPC ID."
  }
}

variable "subnet_id" {
  description = "Existing public subnet with a route to an internet gateway in vpc_id."
  type        = string

  validation {
    condition     = can(regex("^subnet-[0-9a-f]+$", var.subnet_id))
    error_message = "Set an existing public subnet ID."
  }
}

variable "ssh_allowed_cidrs" {
  description = "Explicit public IPv4 /32 addresses allowed to use SSH. Never open SSH globally."
  type        = set(string)

  validation {
    condition = length(var.ssh_allowed_cidrs) > 0 && alltrue([
      for cidr in var.ssh_allowed_cidrs :
      can(cidrnetmask(cidr)) && endswith(cidr, "/32")
    ])
    error_message = "Provide at least one trusted IPv4 /32 CIDR for SSH."
  }
}

variable "ssh_public_key_path" {
  description = "Path to an existing .pub key; private keys are never loaded into Terraform."
  type        = string

  validation {
    condition     = endswith(var.ssh_public_key_path, ".pub") && fileexists(pathexpand(var.ssh_public_key_path))
    error_message = "Set the path to an existing SSH public key (.pub), not a private key."
  }
}

variable "instance_type" {
  description = "Instance size from the project plan."
  type        = string
  default     = "t3.small"

  validation {
    condition     = contains(["t3.small", "t3.medium"], var.instance_type)
    error_message = "Use t3.small or t3.medium as specified in BE #3."
  }
}

variable "root_volume_gb" {
  description = "Encrypted gp3 root disk size."
  type        = number
  default     = 30

  validation {
    condition     = var.root_volume_gb >= 20 && var.root_volume_gb <= 100 && floor(var.root_volume_gb) == var.root_volume_gb
    error_message = "Use a whole-number disk size between 20 and 100 GiB."
  }
}
