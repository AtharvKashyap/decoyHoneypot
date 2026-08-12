"""Centralized model configuration for all Claude API usage in this project.

Keeping the model id in one place makes migrations trivial and keeps every
component (generator, optional adaptive-engagement) on the same model.
"""

# The most capable generally-available Claude model at time of writing.
MODEL = "claude-fable-5"

# Conservative token ceiling for build-time content generation calls.
MAX_TOKENS = 4096
