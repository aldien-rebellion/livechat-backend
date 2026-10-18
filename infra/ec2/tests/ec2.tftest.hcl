mock_provider "aws" {}

override_data {
  target = data.aws_subnet.selected
  values = {
    vpc_id = "vpc-0123456789abcdef0"
  }
}

override_data {
  target = data.aws_ami.ubuntu
  values = {
    id = "ami-0123456789abcdef0"
  }
}

variables {
  aws_region          = "us-east-1"
  vpc_id              = "vpc-0123456789abcdef0"
  subnet_id           = "subnet-0123456789abcdef0"
  ssh_allowed_cidrs   = ["192.0.2.10/32"]
  ssh_public_key_path = "tests/fixtures/deploy.pub"
}

run "secure_server_plan" {
  command = plan

  assert {
    condition     = aws_instance.app.metadata_options[0].http_tokens == "required" && aws_instance.app.root_block_device[0].encrypted
    error_message = "The EC2 plan must require IMDSv2 and encrypted storage."
  }

  assert {
    condition = (
      aws_vpc_security_group_ingress_rule.ssh["192.0.2.10/32"].from_port == 22 &&
      aws_vpc_security_group_ingress_rule.ssh["192.0.2.10/32"].cidr_ipv4 == "192.0.2.10/32" &&
      aws_vpc_security_group_ingress_rule.http.from_port == 80 &&
      aws_vpc_security_group_ingress_rule.https.from_port == 443
    )
    error_message = "Only HTTP/HTTPS and the configured SSH source should be allowed."
  }
}

run "reject_worldwide_ssh" {
  command = plan

  variables {
    ssh_allowed_cidrs = ["0.0.0.0/0"]
  }

  expect_failures = [var.ssh_allowed_cidrs]
}

run "reject_subnet_in_another_vpc" {
  command = plan

  override_data {
    target = data.aws_subnet.selected
    values = {
      vpc_id = "vpc-aaaaaaaaaaaaaaaaa"
    }
  }

  expect_failures = [aws_instance.app]
}
