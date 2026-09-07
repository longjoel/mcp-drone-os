from mcp_drone_os.certificates import issue_host_certificate


def test_certificate_issuer_rejects_invalid_identity(tmp_path):
    ca = tmp_path / "ca"
    ca.write_text("placeholder")
    key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIK1PZlI/P9Uxt54/1imrBksnWHiwVVi4Mg2n236FocCD"
    try:
        issue_host_certificate(key, "bad/id", str(ca))
    except ValueError as error:
        assert "invalid drone id" in str(error)
    else:
        raise AssertionError("invalid identity was accepted")
