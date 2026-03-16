from olly.plan import format_plan, resolve_plan


def test_resolve_plan_and_format(olly_config, backend):
    result = resolve_plan(olly_config, {"primary": backend})
    output = format_plan(result)

    assert "Plan" in output
    assert "Matched schemas" in output
    assert "Matched tables" in output
    assert "main.orders" in output

    # Verify structure: single connection plan
    assert len(result.connection_plans) == 1
    cp = result.connection_plans[0]
    assert cp.name == "primary"
    assert any(m.included and m.name == "main" for m in cp.schema_matches)
    assert "main.orders" in cp.table_matches
    assert "main.customers" in cp.table_matches
