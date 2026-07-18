"""Purpose: Construct a production Flask application with no SQL or authentication.
Directory: app.
Dependencies: Flask, Flask-SocketIO, configuration, JSON stores, Blueprints.
Connection: Central composition root for REST, SocketIO, logging, health, and read-only dashboard.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Flask

from app.api import bp as api_bp
from app.blockchain import BlockchainService
from app.ai.integration import build_ai_pipeline
from app.api.error_handlers import register_error_handlers
from app.api.request_context import register_request_context
from app.api.routes import health_bp
from app.config_loader import LoadedConfiguration, load_platform_configuration
from app.compliance.integration import build_compliance_service
from app.api.routes.compliance import bp as compliance_api_bp
from app.dashboard import bp as dashboard_bp
from app.extensions import socketio
from app.integration import IntegratedPipelineService
from app.hardware.integration import HardwareSecurityPipeline
from app.observability.logging import configure_logging
from app.security.headers import register_security_headers
from app.security.rate_limiting import RateLimiter
from app.storage.audit import AuditReader, AuditWriter
from app.storage.event_store import EventStore
from app.websocket import initialise_websocket

logger = logging.getLogger(__name__)


def _initialise_storage(app: Flask) -> tuple[EventStore, AuditWriter, AuditReader]:
    storage = app.config["PLATFORM_CONFIG"]["storage"]
    event_store = EventStore(
        event_store_root=Path(app.config["EVENT_STORE_ROOT"]),
        index_root=Path(app.config["INDEX_ROOT"]),
        snapshot_root=Path(app.config["SNAPSHOT_ROOT"]),
        lock_root=Path(app.config["LOCK_ROOT"]),
        fsync=bool(storage.get("fsync", True)),
        verify_on_read=bool(storage.get("verify_on_read", True)),
        maximum_event_bytes=int(storage.get("maximum_event_bytes", 1_048_576)),
    )
    audit_writer = AuditWriter(
        Path(app.config["AUDIT_ROOT"]),
        Path(app.config["LOCK_ROOT"]),
        fsync=bool(storage.get("fsync", True)),
    )
    audit_reader = AuditReader(Path(app.config["AUDIT_ROOT"]))
    app.extensions["semisecure.event_store"] = event_store
    app.extensions["semisecure.audit_writer"] = audit_writer
    app.extensions["semisecure.audit_reader"] = audit_reader
    return event_store, audit_writer, audit_reader


def _initialise_socketio(app: Flask, event_store: EventStore) -> None:
    configuration = app.config["PLATFORM_CONFIG"]
    websocket = configuration["websocket"]
    socketio.init_app(
        app,
        async_mode=str(websocket.get("async_mode", "threading")),
        cors_allowed_origins=list(websocket.get("cors_allowed_origins", [])),
        ping_interval=int(websocket.get("ping_interval", 25)),
        ping_timeout=int(websocket.get("ping_timeout", 20)),
        logger=bool(websocket.get("logger", False)),
        engineio_logger=bool(websocket.get("engineio_logger", False)),
        manage_session=False,
    )
    manager, publisher = initialise_websocket(
        socketio=socketio,
        event_store=event_store,
        namespace=str(websocket["namespace"]),
        maximum_replay_events=int(websocket.get("maximum_replay_events", 500)),
        application_version=str(configuration["application"]["version"]),
    )
    app.extensions["semisecure.socket_connections"] = manager
    app.extensions["semisecure.socket_publisher"] = publisher


def _register_cli(app: Flask) -> None:
    @app.cli.command("verify-event-store")
    def verify_event_store_command() -> None:
        report = app.extensions["semisecure.event_store"].verify_all()
        print(report.to_json())
        if not report.valid:
            raise SystemExit(1)

    @app.cli.command("rebuild-event-store")
    def rebuild_event_store_command() -> None:
        report = app.extensions["semisecure.event_store"].rebuild()
        print(report.to_json())
        if not report.valid:
            raise SystemExit(1)


def create_app(
    config_overrides: dict[str, Any] | None = None,
    *,
    project_root: Path | None = None,
) -> Flask:
    loaded: LoadedConfiguration = load_platform_configuration(project_root)
    configure_logging(loaded.values["logging"], loaded.project_root)

    app = Flask(
        __name__,
        template_folder="dashboard/templates",
        static_folder="dashboard/static",
    )
    app.config.update(loaded.flask_mapping())
    app.config.update(
        SECRET_KEY=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=loaded.environment == "production",
        SESSION_COOKIE_SAMESITE="Strict",
        PROPAGATE_EXCEPTIONS=False,
    )
    if config_overrides:
        app.config.update(config_overrides)

    event_store, audit_writer, _ = _initialise_storage(app)
    _initialise_socketio(app, event_store)

    try:
        app.extensions["semisecure.blockchain_service"] = BlockchainService(
            root=loaded.project_root,
            config=dict(loaded.values.get("blockchain", {})),
            event_store=event_store,
            publisher=app.extensions.get("semisecure.socket_publisher"),
        )
    except Exception as exc:
        logger.warning("blockchain_service_unavailable", extra={"error": str(exc)})
        app.extensions["semisecure.blockchain_service"] = None

    try:
        app.extensions["semisecure.ai_pipeline"] = build_ai_pipeline(
            loaded.project_root, dict(loaded.values.get("ai", {}))
        )
    except Exception as exc:
        logger.warning("ai_pipeline_unavailable", extra={"error": str(exc)})
        app.extensions["semisecure.ai_pipeline"] = None

    try:
        app.extensions['semisecure.hardware_pipeline'] = HardwareSecurityPipeline(
            root=loaded.project_root,
            event_store=event_store,
            publisher=app.extensions.get('semisecure.socket_publisher'),
        )
    except Exception as exc:
        logger.warning('hardware_pipeline_unavailable', extra={'error': str(exc)})
        app.extensions['semisecure.hardware_pipeline'] = None

    try:
        app.extensions["semisecure.compliance_service"] = build_compliance_service(
            project_root=loaded.project_root,
            config=dict(loaded.values.get("compliance", {})),
            event_store=event_store,
            publisher=app.extensions.get("semisecure.socket_publisher"),
            blockchain_service=app.extensions.get("semisecure.blockchain_service"),
        )
    except Exception as exc:
        logger.warning("compliance_service_unavailable", extra={"error": str(exc)})
        app.extensions["semisecure.compliance_service"] = None

    rate_limit_config = loaded.values["security"].get("rate_limit", {})
    limiter = RateLimiter(
        requests=int(rate_limit_config.get("requests", 120)),
        window_seconds=int(rate_limit_config.get("window_seconds", 60)),
    )
    app.extensions["semisecure.rate_limiter"] = limiter

    register_request_context(
        app,
        rate_limiter=limiter,
        audit_writer=audit_writer,
        rate_limit_config=rate_limit_config,
    )
    register_security_headers(app, loaded.values["security"])
    register_error_handlers(app)

    app.register_blueprint(api_bp)
    app.register_blueprint(compliance_api_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(dashboard_bp)
    _register_cli(app)

    logger.info(
        "application_created",
        extra={
            "application": loaded.values["application"]["name"],
            "version": loaded.values["application"]["version"],
            "environment": loaded.environment,
            "sql_enabled": False,
            "authentication_enabled": False,
        },
    )

    app.extensions["semisecure.integrated_pipeline"] = (
        IntegratedPipelineService(
            app=app,
            project_root=loaded.project_root,
        )
    )

    return app
