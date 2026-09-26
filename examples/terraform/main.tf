terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  skip_credentials_validation = true
  skip_requesting_account_id  = true
  skip_metadata_api_check     = true

  endpoints {
    ec2        = "http://localhost:4566"
    cloudwatch = "http://localhost:4566"
    elbv2      = "http://localhost:4566"
  }
}

# 1. Production VPC & Subnet
resource "aws_vpc" "production_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = {
    Name        = "production-vpc"
    Environment = "production"
  }
}

resource "aws_subnet" "production_subnet_a" {
  vpc_id            = aws_vpc.production_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
  tags = {
    Name = "production-subnet-a"
  }
}

# 2. Security Group Protecting Live Order Processing Microservice
# PULL REQUEST MUTATION: Inbound port 8080 was removed here by developer!
resource "aws_security_group" "order_service_sg" {
  name        = "order-service-sg"
  description = "Security group for Order Processing Microservice"
  vpc_id      = aws_vpc.production_vpc.id

  # Port 8080 ingress block removed! (Causes immediate network outage on active containers)

  ingress {
    description = "HTTPS health checks"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 3. Compute Instance for Async Worker
# PULL REQUEST MUTATION: Scaled up to t3.xlarge despite idle CPU
resource "aws_instance" "worker_node" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.xlarge" # Upscaled from t3.medium
  subnet_id     = aws_subnet.production_subnet_a.id

  tags = {
    Name        = "order-worker-01"
    Environment = "production"
  }
}
