"""
viz_theme.py — Modular Visualization System (Viridis & Grotesk)
-----------------------------------------------------------------
Shared design tokens and helper functions for the personal chart
library. Every chart archetype script imports from here so that
color, type, and the title/spine/grid treatment stay identical
across completely different chart geometries.

Import this before building any chart:

    from viz_theme import (
        setup_style, viridis_categorical, viridis_continuous,
        style_axes, title_block, BG, TEXT, GRID, MUTED,
    )
    setup_style()  # call once per script, before creating any figure

Design principles (read once, keep in your head):
- ONE background across every chart: plain white (#FFFFFF), never
  off-white/cream and never a different color per chart.
- ONE palette family: viridis, sampled either categorically (discrete
  entities) or continuously (a real scalar like time, magnitude, rank).
  Never hand-roll a bespoke palette per project the way the old
  538 / SCMP / Fortune / NYT reference scripts each did.
- ONE type family: Archivo. Black/Bold for titles, SemiBold for
  subtitles and axis emphasis, Regular for everything else.
- ONE title block shape: bold left-aligned title + lighter subtitle
  directly beneath it, set via figtext, NOT ax.set_title(). This is
  consistent across all six reference scripts and should stay that way.
- Spines off by default. Gridlines are a deliberate design element,
  not matplotlib's default gray — they get the same GRID token
  everywhere, thin, and always set_axisbelow(True).
"""

import os
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import to_hex
import matplotlib as mpl

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_FONT_DIR = os.path.normpath(_FONT_DIR)

FONT_BLACK = "Archivo Black"      # hero titles only
FONT_BOLD = "Archivo Bold"        # section titles, strong emphasis, entity labels
FONT_SEMIBOLD = "Archivo SemiBold"  # subtitles, axis titles, legends
FONT_REGULAR = "Archivo"          # body text, tick labels, annotations

_FONTS_REGISTERED = False


def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    for fname in ("Archivo-Regular.ttf", "Archivo-SemiBold.ttf",
                  "Archivo-Bold.ttf", "Archivo-Black.ttf"):
        path = os.path.join(_FONT_DIR, fname)
        if os.path.exists(path):
            fm.fontManager.addfont(path)
    _FONTS_REGISTERED = True


# --------------------------------------------------------------------------
# Color tokens
# --------------------------------------------------------------------------
BG = "#FFFFFF"        # plain white — use for fig + ax facecolor, always
PANEL_BG = "#EDEBE2"  # slightly deeper card/panel background, for insets or ribbons
TEXT = "#1B1B18"      # near-black, warmer than pure #000 to sit on BG
MUTED = "#6B6A63"     # subtitles, secondary annotations, de-emphasized labels
GRID = "#D8D5C9"      # gridlines — warm gray-beige, not matplotlib default gray

VIRIDIS = plt.get_cmap("viridis")


def viridis_categorical(n, low=0.08, high=0.92):
    """N discrete colors sampled evenly across viridis for categorical
    entities (clusters, actors, ribbons). Avoid the very ends (pure
    yellow/pure purple) unless you want maximum contrast — the default
    low/high keeps things a bit richer and more print-friendly."""
    if n == 1:
        return [to_hex(VIRIDIS(0.5))]
    return [to_hex(VIRIDIS(low + (high - low) * i / (n - 1))) for i in range(n)]


def viridis_continuous(t):
    """t in [0, 1] -> hex color. Use for anything that's a REAL scalar:
    a year, a rank, a magnitude — not an arbitrary category order."""
    t = max(0.0, min(1.0, t))
    return to_hex(VIRIDIS(t))


# --------------------------------------------------------------------------
# Global rcParams
# --------------------------------------------------------------------------
def setup_style():
    """Call once at the top of every chart script, before plt.subplots()."""
    _register_fonts()
    mpl.rcParams["font.family"] = FONT_REGULAR
    mpl.rcParams["text.color"] = TEXT
    mpl.rcParams["axes.edgecolor"] = GRID
    mpl.rcParams["axes.labelcolor"] = TEXT
    mpl.rcParams["xtick.color"] = MUTED
    mpl.rcParams["ytick.color"] = MUTED
    mpl.rcParams["figure.facecolor"] = BG
    mpl.rcParams["axes.facecolor"] = BG
    mpl.rcParams["savefig.facecolor"] = BG


# --------------------------------------------------------------------------
# Shared component helpers
# --------------------------------------------------------------------------
def style_axes(ax, grid_axis="both", spines_visible=None):
    """The signature spine/grid treatment used across every archetype:
    spines off, gridlines behind the data in the warm GRID tone, ticks
    with no dash marks. Pass spines_visible=['left','bottom'] etc. if
    a specific chart genuinely needs an anchor axis (rare — most of the
    reference scripts strip all four)."""
    spines_visible = spines_visible or []
    for name, spine in ax.spines.items():
        spine.set_visible(name in spines_visible)
    if grid_axis:
        ax.grid(True, axis=grid_axis, color=GRID, linestyle="-",
                linewidth=1.2, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", which="major", labelsize=11,
                    colors=MUTED, length=0)
    return ax


def title_block(fig, title, subtitle=None, x=0.06, y_title=0.96, y_sub=0.915,
                 title_size=22, subtitle_size=13):
    """The one title shape every chart in this system uses: bold/black
    left-aligned title, lighter SemiBold-weight subtitle directly under
    it. Always figtext, never ax.set_title() — keeps title position
    stable regardless of subplot layout."""
    fig.text(x, y_title, title, fontsize=title_size, fontfamily=FONT_BOLD,
              color=TEXT)
    if subtitle:
        fig.text(x, y_sub, subtitle, fontsize=subtitle_size,
                  fontfamily=FONT_SEMIBOLD, color=MUTED)


def footer_config(fig, text, x=0.06, y=0.02, size=9.5):
    """Small config/attribution line at the bottom — mirrors the
    'CONFIGURATION: ...' footer in the reference mockup."""
    fig.text(x, y, text, fontsize=size, fontfamily=FONT_SEMIBOLD,
             color=MUTED, ha="left")
