terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket  = "terraform-mcp-state-060274391205"
    key     = "production/terraform.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = "us-east-1"
}

# 1. Production VPC & Subnets (Multi-AZ)
resource "aws_vpc" "production_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  tags = {
    Name        = "production-vpc"
    Environment = "production"
    ManagedBy   = "Terraform-MCP"
  }
}

resource "aws_subnet" "production_subnet_a" {
  vpc_id            = aws_vpc.production_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
  tags = {
    Name        = "production-subnet-a"
    Environment = "production"
  }
}

resource "aws_subnet" "production_subnet_b" {
  vpc_id            = aws_vpc.production_vpc.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
  tags = {
    Name        = "production-subnet-b"
    Environment = "production"
  }
}

# 2. Security Group for Order Processing Microservice (Maintained)
resource "aws_security_group" "order_service_sg" {
  name        = "order-service-sg"
  description = "Security group for Order Processing Microservice"
  vpc_id      = aws_vpc.production_vpc.id

  ingress {
    description = "Order processing REST API"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  ingress {
    description = "HTTPS health checks"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    description = "Outbound egress to internal services"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "order-service-sg"
    Environment = "production"
  }
}

# 3. Security Group for Analytics & Telemetry Service (New Microservice)
resource "aws_security_group" "analytics_service_sg" {
  name        = "analytics-service-sg"
  description = "Security group for Analytics and Telemetry Microservice"
  vpc_id      = aws_vpc.production_vpc.id

  ingress {
    description = "Analytics ingestion endpoint"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  ingress {
    description = "HTTPS telemetry"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "analytics-service-sg"
    Environment = "production"
  }
}

# 4. Compute Worker Instance (FinOps Waste Mutation)
# Upscaled to t3.xlarge from baseline t3.medium despite idle P99 CPU (12.4%)
resource "aws_instance" "order_worker" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.xlarge"
  subnet_id     = aws_subnet.production_subnet_a.id

  tags = {
    Name        = "i-order-worker-01"
    Environment = "production"
  }
}
