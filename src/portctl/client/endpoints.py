"""Port API endpoint URL constants."""

from __future__ import annotations

PORT_API_BASE_URL = "https://api.getport.io/v1"

# Auth
AUTH_TOKEN = "/auth/access_token"

# Blueprints
BLUEPRINTS = "/blueprints"
BLUEPRINT_BY_ID = "/blueprints/{identifier}"

# Scorecards
SCORECARDS = "/blueprints/{blueprint_id}/scorecards"
SCORECARD_BY_ID = "/blueprints/{blueprint_id}/scorecards/{identifier}"

# Actions (top-level — /blueprints/{id}/actions is deprecated since 2025)
ACTIONS = "/actions"
ACTION_BY_ID = "/actions/{identifier}"

# Pages
PAGES = "/pages"
PAGE_BY_ID = "/pages/{identifier}"

# Entities
ENTITIES = "/blueprints/{blueprint_id}/entities"
ENTITY_BY_ID = "/blueprints/{blueprint_id}/entities/{identifier}"

# Integrations
INTEGRATIONS = "/integrations"
INTEGRATION_LOGS = "/integrations/{integration_id}/logs"

# User
ME = "/me"
