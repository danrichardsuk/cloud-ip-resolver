from cloud_ip_resolver.compare import compare_gcp_csv
from cloud_ip_resolver.io import GCP_OUTPUT_FIELDS


def test_compare_gcp_ignores_order_and_preserves_duplicates(tmp_path) -> None:
    header = ",".join(GCP_OUTPUT_FIELDS) + "\n"
    row1 = "34.80.10.20,34.80.0.0/16,Google Cloud,asia-east1-special\n"
    row2 = "34.80.10.20,34.80.0.0/15,Google Cloud,asia-east1\n"
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    old.write_text(header + row1 + row2 + row2, encoding="utf-8")
    new.write_text(header + row2 + row1 + row2, encoding="utf-8")
    only_old, only_new = compare_gcp_csv(old, new)
    assert not only_old
    assert not only_new
