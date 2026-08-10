import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import PlainTextResponse


def _render_metric_lines(
    metric_name: str,
    metric_help: str,
    metric_type: str,
    values: dict[tuple[str, str, int], int | float],
    *,
    format_value: str = "{}",
) -> list[str]:
    lines = [
        f"# HELP {metric_name} {metric_help}",
        f"# TYPE {metric_name} {metric_type}",
    ]
    for (method, path, status_code), value in sorted(values.items()):
        rendered_value = format_value.format(value)
        lines.append(
            f'{metric_name}{{method="{method}",path="{path}",status="{status_code}"}} {rendered_value}'
        )
    return lines


@dataclass(slots=True)
class MetricsRegistry:
    requests_total: dict[tuple[str, str, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    duration_sum_seconds: dict[tuple[str, str, int], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    duration_count: dict[tuple[str, str, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    errors_total: dict[tuple[str, str, int], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    lock: Lock = field(default_factory=Lock)

    def record(
        self, *, method: str, path: str, status_code: int, duration: float
    ) -> None:
        key = (method, path, status_code)
        with self.lock:
            self.requests_total[key] += 1
            self.duration_sum_seconds[key] += duration
            self.duration_count[key] += 1
            if status_code >= 400:
                self.errors_total[key] += 1

    def render_prometheus(self) -> str:
        lines: list[str] = []
        lines.extend(
            _render_metric_lines(
                "http_requests_total",
                "Total number of HTTP requests",
                "counter",
                self.requests_total,  # type: ignore
            )
        )
        lines.extend(
            _render_metric_lines(
                "http_request_duration_seconds_sum",
                "Total HTTP request duration in seconds",
                "counter",
                self.duration_sum_seconds,
                format_value="{:.6f}",
            )
        )
        lines.extend(
            _render_metric_lines(
                "http_request_duration_seconds_count",
                "Total number of measured HTTP requests",
                "counter",
                self.duration_count,  # type: ignore
            )
        )
        lines.extend(
            _render_metric_lines(
                "http_errors_total",
                "Total number of HTTP errors",
                "counter",
                self.errors_total,  # type: ignore
            )
        )

        return "\n".join(lines) + "\n"


def register_metrics(app: FastAPI) -> None:
    registry = MetricsRegistry()
    app.state.metrics_registry = registry

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - started
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        registry.record(
            method=request.method,
            path=path,
            status_code=response.status_code,
            duration=elapsed,
        )
        return response

    metrics_router = APIRouter()

    @metrics_router.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> PlainTextResponse:
        return PlainTextResponse(
            content=registry.render_prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    app.include_router(metrics_router)
