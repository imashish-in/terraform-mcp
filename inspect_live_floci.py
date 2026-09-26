import json
import urllib.request
import boto3

def inspect_floci():
    endpoint = "http://localhost:4566"
    
    print("==========================================================")
    print(" LIVE FLOCI EMULATOR INSPECTION")
    print("==========================================================")
    
    # 1. Check Health Endpoint
    try:
        with urllib.request.urlopen(f"{endpoint}/_floci/health") as response:
            health_data = json.loads(response.read().decode())
            print(f"✔ Status: {health_data.get('status', 'OK')}")
            print(f"✔ Uptime: {health_data.get('uptime', 'N/A')}")
            print(f"✔ Services: {list(health_data.get('services', {}).keys())}")
    except Exception as e:
        print(f"Health check: {e}")

    # 2. Query Live EC2 State
    ec2 = boto3.client("ec2", endpoint_url=endpoint, region_name="us-east-1")
    
    print("\n--- Live Security Groups ---")
    sgs = ec2.describe_security_groups()["SecurityGroups"]
    for sg in sgs:
        print(f" • {sg['GroupId']} ({sg['GroupName']})")
        print(f"   Description: {sg['Description']}")

    print("\n--- Live Attached ENIs (Workloads) ---")
    enis = ec2.describe_network_interfaces()["NetworkInterfaces"]
    for eni in enis:
        groups = [g['GroupId'] for g in eni.get('Groups', [])]
        print(f" • {eni['NetworkInterfaceId']} [IP: {eni.get('PrivateIpAddress')}]")
        print(f"   Status: {eni.get('Status')} | Bound SGs: {groups}")
        print(f"   Task / Description: {eni.get('Description')}")

    print("==========================================================")

if __name__ == "__main__":
    inspect_floci()
