from services.api_gateway.app.main import app


def test_workflow_routes_removed():
    paths = {route.path for route in app.router.routes}
    assert "/v1/workflows" not in paths
    assert "/v1/workflows/status/{workflow_id}" not in paths
