"""Port API endpoint URL constants."""

from __future__ import annotations

PORT_API_BASE_URL = "https://api.getport.io/v1"

# Auth
AUTH_TOKEN = "/auth/access_token"

# Blueprints
BLUEPRINTS = "/blueprints"
BLUEPRINT_BY_ID = "/blueprints/{identifier}"

# Scorecards
SCORECARDS = "/blueprints/{blueprint}/scorecards"
SCORECARD_BY_ID = "/blueprints/{blueprint}/scorecards/{identifier}"

# Actions
ACTIONS = "/blueprints/{blueprint}/actions"
ACTION_BY_ID = "/blueprints/{blueprint}/actions/{identifier}"

# Pages
PAGES = "/pages"
PAGE_BY_ID = "/pages/{identifier}"
