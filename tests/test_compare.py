from pathlib import Path

from cloud_ip_resolver.compare import compare_aws_csv

HEADER = "IPAddress,Prefix,Region,Service,NetworkBorderGroup\n"


def test_compare_aws_csv_ignores_row_order(tmp_path: Path) -> None:
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    row1 = "198.51.100.10,198.51.100.0/25,us-east-1,EC2,us-east-1\n"
    row2 = "198.51.100.10,198.51.100.0/24,us-east-1,AMAZON,us-east-1\n"
    old.write_text(HEADER + row1 + row2, encoding="utf-8")
    new.write_text(HEADER + row2 + row1, encoding="utf-8")

    only_old, only_new = compare_aws_csv(old, new)

    assert not only_old
    assert not only_new
