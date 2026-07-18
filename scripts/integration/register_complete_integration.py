"""Register the integrated pipeline service and API blueprint."""

from pathlib import Path


root = Path(".").resolve()

factory_path = root / "app/factory.py"
factory = factory_path.read_text(
    encoding="utf-8"
)

service_import = (
    "from app.integration import "
    "IntegratedPipelineService\n"
)

if service_import not in factory:
    anchor = (
        "from app.extensions import"
    )
    position = factory.find(anchor)

    if position < 0:
        raise SystemExit(
            "Could not find factory import section"
        )

    line_end = factory.find(
        "\n",
        position,
    )

    factory = (
        factory[: line_end + 1]
        + service_import
        + factory[line_end + 1 :]
    )

service_block = '''
    app.extensions["semisecure.integrated_pipeline"] = (
        IntegratedPipelineService(
            app=app,
            project_root=loaded.project_root,
        )
    )
'''

if (
    'app.extensions["semisecure.integrated_pipeline"]'
    not in factory
):
    marker = (
        '    logger.info("application_created"'
    )
    position = factory.find(marker)

    if position < 0:
        marker = "    return app\n"
        position = factory.find(marker)

    if position < 0:
        raise SystemExit(
            "Could not locate factory registration point"
        )

    factory = (
        factory[:position]
        + service_block
        + "\n"
        + factory[position:]
    )

factory_path.write_text(
    factory,
    encoding="utf-8",
)


routes_path = root / "app/api/routes/__init__.py"
routes = routes_path.read_text(
    encoding="utf-8"
)

route_import = (
    "from app.api.routes.integration "
    "import bp as integration_bp\n"
)

if route_import not in routes:
    routes = (
        route_import
        + routes
    )

if "integration_bp" not in routes.split(
    "VERSIONED_BLUEPRINTS",
    1,
)[-1]:
    marker = "VERSIONED_BLUEPRINTS = ["

    if marker not in routes:
        marker = "VERSIONED_BLUEPRINTS = ("

    position = routes.find(marker)

    if position < 0:
        raise SystemExit(
            "VERSIONED_BLUEPRINTS was not found"
        )

    opening_end = position + len(marker)

    routes = (
        routes[:opening_end]
        + "\n    integration_bp,"
        + routes[opening_end:]
    )

routes_path.write_text(
    routes,
    encoding="utf-8",
)

print("Complete integration service registered")
