from api.app import create_app

from api_helpers import SECRET


def test_every_schema_has_a_unique_plain_name():
    """Two routers defining the same model name make OpenAPI rename both with a module prefix
    (api__routers__x__Name), which silently breaks the generated TypeScript types. Keep names unique."""
    app = create_app(SECRET, session_factory=lambda: None, session_timeout_hours=1)
    clashes = [name for name in app.openapi()["components"]["schemas"] if "__" in name]
    assert clashes == []
