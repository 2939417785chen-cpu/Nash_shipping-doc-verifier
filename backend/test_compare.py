"""Run with: python backend/test_compare.py   (prints 'All tests passed' when fine)"""
from compare import compare_field, compare_fields, normalize_name, normalize_port


def fields(**values):
    base = {"shipper": "ACME TRADING SDN BHD", "consignee": "BLUE OCEAN LLC",
            "notify_party": "BLUE OCEAN LLC", "port_of_loading": "NANTONG, CHINA",
            "port_of_discharge": "KARACHI, PAKISTAN", "container_count": 3,
            "gross_weight_kg": 22000}
    base.update(values)
    return {k: {"value": v, "evidence": ""} for k, v in base.items()}


# 1. The example from the task: 3 vs 4 containers, everything else the same
result = compare_fields(fields(), fields(container_count=4))
assert result["defect_fields"] == ["container_count"]
item = [c for c in result["comparisons"] if c["field"] == "container_count"][0]
assert (item["si_value"], item["bl_value"], item["match"]) == (3, 4, False)

# 2. All seven fields match -> no defects
assert compare_fields(fields(), fields())["defect_fields"] == []

# 3. Format differences are NOT defects
assert compare_field("shipper", "APRIL FAR EAST (M) SDN BHD", "April Far East (M) Sdn. Bhd.")["match"]
assert compare_field("consignee", "EAST BRIGHT FZ-LLC", "EAST BRIGHT FZ LLC")["match"]
assert compare_field("shipper", "ACME COMPANY LIMITED", "ACME CO., LTD.")["match"]
assert compare_field("shipper", "ACME & SONS", "ACME AND SONS")["match"]
assert compare_field("port_of_loading", "NANTONG, CHINA", "NANTONG")["match"]
assert compare_field("port_of_loading", "NANTONG, CHINA", "NANTONG PORT, JIANGSU, CHINA (CNNTG)")["match"]
assert compare_field("gross_weight_kg", 22000, 22000.0)["match"]

# 4. Real differences ARE defects
assert compare_field("consignee", "EAST BRIGHT FZ-LLC", "UAB NOVAKOPA")["match"] is False
assert compare_field("port_of_discharge", "KARACHI, PAKISTAN", "PORT KLANG, MALAYSIA")["match"] is False
assert compare_field("port_of_loading", "NANTONG, CHINA", "NANTONG, VIETNAM")["match"] is False
assert compare_field("gross_weight_kg", 22000, 22100)["match"] is False

# 5. A missing value cannot be judged: match is None, listed as missing (not as a defect)
result = compare_fields(fields(), fields(gross_weight_kg=None))
assert result["missing_fields"] == ["gross_weight_kg"] and result["defect_fields"] == []

# 6. Look-alike names: different, but a person should look
close = compare_field("shipper", "ACME TRADING SDN BHD", "ACME TRADING SDN BHD MALAYSIA")
assert close["match"] is False and close["confidence"] == 0.6
far = compare_field("shipper", "ACME TRADING SDN BHD", "ZEBRA LOGISTICS PTE")
assert far["match"] is False and far["confidence"] == 0.95

# 7. Evidence is passed along for the review page
si = fields(); si["consignee"]["evidence"] = "Consignee: BLUE OCEAN LLC"
comparison = compare_fields(si, fields())["comparisons"][1]
assert comparison["si_evidence"]["snippet"] == "Consignee: BLUE OCEAN LLC"

print("All tests passed")