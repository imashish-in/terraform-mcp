from pathlib import Path
from terraform_mcp.plan_parser import parse_terraform_plan

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_parse_case_a_port_revocation():
    plan_path = FIXTURES_DIR / "case_a_port_revocation.json"
    parsed = parse_terraform_plan(plan_path.read_text(encoding="utf-8"))

    assert parsed.format_version == "1.2"
    assert len(parsed.security_group_changes) == 1

    sg_change = parsed.security_group_changes[0]
    assert sg_change.resource_id == "sg-0a1b2c3d4e5f60718"
    assert 8080 in sg_change.revoked_ports
    assert sg_change.actions == ["update"]


def test_parse_case_b_compute_upsize():
    plan_path = FIXTURES_DIR / "case_b_compute_upsize.json"
    parsed = parse_terraform_plan(plan_path.read_text(encoding="utf-8"))

    assert len(parsed.compute_resizes) == 1
    resize = parsed.compute_resizes[0]
    assert resize.resource_id == "i-0987654321fedcba0"
    assert resize.current_type == "t3.medium"
    assert resize.proposed_type == "t3.xlarge"


def test_parse_case_c_route_modification():
    plan_path = FIXTURES_DIR / "case_c_route_modification.json"
    parsed = parse_terraform_plan(plan_path.read_text(encoding="utf-8"))

    assert len(parsed.route_changes) == 1
    route = parsed.route_changes[0]
    assert route.route_table_id == "rtb-0a1b2c3d4e5f67890"
    assert route.destination_cidr == "10.200.0.0/16"
    assert route.has_vpc_endpoint is False
