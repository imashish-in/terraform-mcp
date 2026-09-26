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

# 1. Production VPC & Subnet
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

# 2. Security Group for Order Processing Microservice
resource "aws_security_group" "order_service_sg" {
  name        = "order-service-sg"
  description = "Security group for Order Processing Microservice"
  vpc_id      = aws_vpc.production_vpc.id

  # Inbound port for order processing API service
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
