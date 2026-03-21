"""
Catppuccin Mocha palette constants for Rich-based terminal output.

Hex values sourced from https://catppuccin.com/palette (Mocha flavour).
"""

# ── Accent colours ────────────────────────────────────────────────────────────
ROSEWATER = "#f5e0dc"
FLAMINGO  = "#f2cdcd"
PINK      = "#f5c2e7"
MAUVE     = "#cba6f7"
RED       = "#f38ba8"
MAROON    = "#eba0ac"
PEACH     = "#fab387"
YELLOW    = "#f9e2af"
GREEN     = "#a6e3a1"
TEAL      = "#94e2d5"
SKY       = "#89dceb"
SAPPHIRE  = "#74c7ec"
BLUE      = "#89b4fa"
LAVENDER  = "#b4befe"

# ── Text / overlay colours ────────────────────────────────────────────────────
TEXT      = "#cdd6f4"
SUBTEXT1  = "#bac2de"
SUBTEXT0  = "#a6adc8"
OVERLAY2  = "#9399b2"
OVERLAY1  = "#7f849c"
OVERLAY0  = "#6c7086"

# ── Surface / base colours ────────────────────────────────────────────────────
SURFACE2  = "#585b70"
SURFACE1  = "#45475a"
SURFACE0  = "#313244"
BASE      = "#1e1e2e"
MANTLE    = "#181825"
CRUST     = "#11111b"

# ── Semantic aliases used across _report.py and cli.py ───────────────────────
CREATED   = GREEN    # new snapshot files
UPDATED   = BLUE     # overwritten snapshot files
UNUSED    = YELLOW   # on-disk files not accessed this session
PRUNED    = RED      # deleted files

TITLE     = MAUVE    # panel / table titles
HEADER    = LAVENDER # table column headers
MUTED     = OVERLAY1 # dim / secondary text
ACCENT    = PEACH    # highlights, warnings, interactive prompts
PATH      = SAPPHIRE # file paths
