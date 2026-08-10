"""Public HTTP API surface for the imports bounded context.

This package exposes the top-level imports router that is mounted by the
application root router. Resource-specific routes are composed under
imports_router to keep the URL contract stable while allowing internal
router decomposition.
"""

from app.modules.imports.http.router import imports_router

__all__ = ["imports_router"]
