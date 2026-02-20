from olly.explain import explain_config, format_explain


def test_explain_config_and_format(olly_config, backend):
    result = explain_config(olly_config, {"primary": backend})
    output = format_explain(result)

    assert "Config explain" in output
    assert "Matched schemas" in output
    assert "Matched tables" in output
    assert "main.orders" in output

    # Verify structure: single connection explain
    assert len(result.connection_explains) == 1
    ce = result.connection_explains[0]
    assert ce.name == "primary"
    assert any(m.included and m.name == "main" for m in ce.schema_matches)
    assert "main.orders" in ce.table_matches
    assert "main.customers" in ce.table_matches
