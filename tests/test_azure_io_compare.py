"""Tests for Azure legacy CSV writing and parity comparison.

These checks protect the contract with existing analyst output files: the Python
rewrite may be faster internally, but its Azure-specific CSV must retain the
same columns and comparison must not fail solely because rows were reordered.
"""

import csv

from cloud_ip_resolver.compare import compare_azure_csv
from cloud_ip_resolver.io import AZURE_OUTPUT_FIELDS, write_azure_matches_csv
from cloud_ip_resolver.models import CloudPrefix
from cloud_ip_resolver.resolver import Resolver


def test_write_azure_matches_uses_legacy_columns(tmp_path) -> None:
    """Map a normalised Azure prefix back to the exact historical CSV schema."""

    prefix = CloudPrefix.from_cidr(
        provider="Azure",
        cidr="20.1.0.0/16",
        service="Storage",
        region="westeurope",
        scope="Storage.WestEurope",
        metadata={
            "name": "Storage.WestEurope",
            "published_prefix": "20.1.0.0/16",
            "network_features": "API;NSG",
        },
    )
    output = tmp_path / "out.csv"
    resolutions = [Resolver([prefix]).resolve_one("20.1.2.3")]

    rows = write_azure_matches_csv(output, resolutions)

    assert rows == 1
    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        row = next(reader)

    assert tuple(reader.fieldnames or ()) == AZURE_OUTPUT_FIELDS
    assert row == {
        "IPAddress": "20.1.2.3",
        "Name": "Storage.WestEurope",
        "Prefix": "20.1.0.0/16",
        "Region": "westeurope",
        "SystemService": "Storage",
        "NetworkFeatures": "API;NSG",
    }


def test_compare_azure_ignores_order(tmp_path) -> None:
    """Treat the same Azure rows in a different order as exact parity."""

    header = ",".join(AZURE_OUTPUT_FIELDS) + "\n"
    row1 = "20.1.2.3,Storage.WestEurope,20.1.0.0/16,westeurope,Storage,API;NSG\n"
    row2 = "20.1.2.3,AzureCloud.westeurope,20.0.0.0/8,westeurope,,\n"
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    old.write_text(header + row1 + row2, encoding="utf-8")
    new.write_text(header + row2 + row1, encoding="utf-8")

    only_old, only_new = compare_azure_csv(old, new)

    assert not only_old
    assert not only_new
