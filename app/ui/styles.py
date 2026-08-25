"""Shared visual style for the desktop UI.

A single stylesheet keeps every screen visually consistent.

Second reskin pass (2026-08-25): the user supplied a fuller reference
implementation ("PetrolStream ERP", a Google AI-Studio React/TS mockup) and
asked every screen to match it as closely as possible - a black-on-off-white
system, softly-shadowed 24px-rounded white cards on a slightly darker page
canvas, hairline `#e5e5e5` borders (not the previous palette's solid black
card borders), pill-shaped buttons (kept - it already matched), and color
used ONLY for status meaning, never decoration: red for danger/alerts/low
stock, emerald for success/positive trends, and one narrower amber tier for
"notable but not critical" (this app's own existing WARNING severity, an
amber the mockup itself also uses for a down-trend indicator). The previous
palette's Signal Orange/Chartreuse Highlight - used everywhere as a plain
decorative accent (KPI numeral color, hover borders, active-nav indicators)
- are retired entirely; the reference has no decorative accent color at all,
so those roles become plain black/white/grey instead of recolored.

Dark mode (2026-08-24, carried forward unchanged in shape): a second
variant of the same system rather than a bolt-on inversion filter:
  - The page canvas and card surface, identical in light mode (both read as
    the same near-white, distinguished only by border+shadow), CANNOT stay
    identical in dark mode: a hairline-bordered card on a black page would
    be nearly invisible. Page = Carbon Black, card = Graphite.
  - Steel/Ash swap which one is "muted" vs "faint": a LIGHTER grey reads as
    more prominent against a dark background and a DARKER grey recedes
    more, the opposite of how they read against a near-white page.
  - The filled/primary button inverts fill and text (Paper White fill on
    dark, not Carbon Black) since a black button on a black page would
    disappear.
  - The card shadow and the dot-grid texture are literally black-on-
    transparent by default (`apply_hard_shadow`, `GridBackgroundWidget`) -
    both check `app.ui.theme.is_dark_mode()` and switch to a visible tone
    automatically, no call-site changes needed anywhere else in the app.
  - Danger/success/caution got real dark variants (lighter text, dark muted
    fill) rather than reusing the light-mode pastel fills, which would
    glare against a dark page.
  - The persistent left sidebar and the table header bar used to be fixed
    dark surfaces regardless of theme (matching an earlier client
    reference). The PetrolStream reference's own sidebar and table headers
    are light, plain panels, so both are now theme-aware like everything
    else instead of permanently dark - see the sidebar/table-header blocks
    below.

Recorded assumptions (the source mockup has no equivalent, so these are
carried over or reasoned from context rather than invented from nothing):
  - The mockup has no dark mode at all; this app's existing dark mode is
    preserved and re-themed to the new palette rather than dropped.
  - `Geist`/`Geist Mono` are Vercel's proprietary web fonts (the mockup's
    own font choice). This is an offline desktop app with no internet
    access and no bundled font files, so there is nothing to actually load
    them from. QSS font-family falls through to the fallback chain, which
    lands on "Segoe UI" on Windows - a similar-weight, geometric sans
    already installed on every target machine.
  - The mockup uses amber only once (a down-trend arrow color); this app
    already has a real three-tier severity model (NORMAL/WARNING/
    INVESTIGATION_REQUIRED/APPROVAL_REQUIRED, collapsed to normal/warning/
    critical) that genuinely needs a middle tone between "fine" and
    "critical" - amber fills that real, pre-existing need rather than being
    decoration.
"""

# --- Design tokens ---

COLOR_ALERT_RED = "#e7000b"      # danger / critical / low-stock - the mockup's own red
COLOR_CAUTION_AMBER = "#d97706"  # notable-but-not-critical (this app's WARNING tier)
COLOR_CAUTION_BG = "#fef3c7"
COLOR_CAUTION_TEXT = "#92400e"
COLOR_CARBON_BLACK = "#000000"
COLOR_PAPER_WHITE = "#fafafa"
COLOR_GRAPHITE = "#242424"
COLOR_STEEL = "#6c6c6c"
COLOR_ASH = "#b3b3b3"

FONT_SANS = "'Geist', 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif"
FONT_MONO = "'Geist Mono', 'Consolas', 'Cascadia Mono', monospace"

RADIUS_MD = 4       # radius-smallbuttons
RADIUS_LG = 8        # radius-links / inputs
RADIUS_XL = 24       # radius-cards - bumped 12->24 to match the mockup's rounded-[24px] cards
RADIUS_FULL = 9999   # radius-buttons / radius-tags (pill) - already matched, unchanged

# A neutral (not color-tinted) selection wash for text/table selection -
# replaces the previous palette's orange-tinted selection color, since the
# new system reserves color for status meaning only.
COLOR_SELECTION_WASH = "#eeeeee"

# The card shadow's default color, when a call site does not override it -
# see apply_hard_shadow() in app/ui/qt_utils.py, which picks between this
# and DARK_SHADOW_COLOR based on the active theme. Applied at low opacity
# by apply_hard_shadow() itself (a soft, barely-there elevation, not a
# heavy shadow) - see that function's docstring.
LIGHT_SHADOW_COLOR = "#000000"
DARK_SHADOW_COLOR = "#8a8a8a"

# The dot-grid texture's default color for each mode - see
# GridBackgroundWidget in app/ui/widgets.py.
LIGHT_DOT_COLOR = (0, 0, 0, 13)      # ~5% opacity black, matching the mockup's own faint radial-dot page background
DARK_DOT_COLOR = (255, 255, 255, 18)  # a touch stronger; white specks read fainter at equal opacity


def build_stylesheet(dark: bool = False) -> str:
    """Returns the app's full QSS stylesheet for the given mode.

    Every color below is a local variable, not a module constant, so the
    exact same template can serve both modes - only the values assigned
    here differ per mode; the QSS selectors and structure are identical.
    """

    if dark:
        # Page canvas vs. card surface must differ (unlike light mode)
        # or a hairline-bordered card on a black page would be invisible.
        color_bg = COLOR_CARBON_BLACK
        color_surface = COLOR_GRAPHITE
        color_border = COLOR_STEEL
        color_text = COLOR_PAPER_WHITE
        # Ash/Steel swap roles - see module docstring.
        color_text_muted = COLOR_ASH
        color_text_faint = COLOR_STEEL

        color_primary = COLOR_PAPER_WHITE
        color_primary_hover = COLOR_ASH
        color_primary_pressed = COLOR_PAPER_WHITE
        color_primary_text = COLOR_CARBON_BLACK

        color_surface_hover = "#333333"
        color_disabled_bg = "#3a3a3a"
        color_disabled_text = COLOR_STEEL

        color_danger = "#f87171"
        color_danger_bg = "#3a1414"
        color_danger_hover = "#fca5a5"
        color_success = "#34d399"
        color_success_bg = "#0f2a1f"
        color_caution = "#fbbf24"
        color_caution_bg = "#3a2a0a"
        color_caution_text = "#fde68a"
    else:
        color_bg = "#f9f9f9"
        color_surface = "#ffffff"
        color_border = "#e5e5e5"
        color_text = "#1a1c1c"
        color_text_muted = "#5f5e5e"
        color_text_faint = "#a3a3a3"

        # Filled buttons stay Carbon Black - "the strongest visual anchor,"
        # matching the mockup's own black pill buttons throughout.
        color_primary = COLOR_CARBON_BLACK
        color_primary_hover = "#262626"
        color_primary_pressed = COLOR_CARBON_BLACK
        color_primary_text = "#ffffff"

        color_surface_hover = "#f3f3f3"
        color_disabled_bg = "#e5e5e5"
        color_disabled_text = "#ffffff"

        color_danger = COLOR_ALERT_RED
        color_danger_bg = "#ffebee"
        color_danger_hover = "#c40009"
        color_success = "#059669"
        color_success_bg = "#ecfdf5"
        color_caution = COLOR_CAUTION_AMBER
        color_caution_bg = COLOR_CAUTION_BG
        color_caution_text = COLOR_CAUTION_TEXT

    return f"""
* {{
    font-family: {FONT_SANS};
    font-size: 14px;
    color: {color_text};
}}

QMainWindow, QWidget#background {{
    background-color: {color_bg};
}}

QWidget#card {{
    background-color: {color_surface};
    border: 1px solid {color_border};
    border-radius: {RADIUS_XL}px;
}}

QLabel#title {{
    font-size: 24px;
    font-weight: 700;
    color: {color_text};
}}

QLabel#subtitle {{
    font-size: 14px;
    color: {color_text_muted};
}}

QLabel#errorLabel {{
    color: {color_danger};
    background-color: {color_danger_bg};
    border: 1px solid {color_danger};
    border-radius: {RADIUS_LG}px;
    padding: 8px;
    font-size: 12px;
}}

/* A one-line, genuinely time-sensitive notice - amber (this app's WARNING
   tier), the same tone alertTag/alertCard use for the same severity. */
QLabel#warningLabel {{
    color: {color_caution_text};
    background-color: {color_caution_bg};
    border: 1px solid {color_caution};
    border-radius: {RADIUS_LG}px;
    padding: 8px;
}}

QLineEdit {{
    background-color: {color_surface};
    border: 1.5px solid {color_border};
    border-radius: {RADIUS_MD}px;
    padding: 10px 12px;
    font-size: 14px;
    selection-background-color: {COLOR_SELECTION_WASH};
}}

QLineEdit:focus {{
    border: 2px solid {color_text};
}}

QPushButton {{
    background-color: {color_primary};
    color: {color_primary_text};
    border: 1.5px solid {color_border};
    border-radius: {RADIUS_FULL}px;
    padding: 10px 18px;
    font-size: 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {color_primary_hover};
}}

QPushButton:pressed {{
    background-color: {color_primary_pressed};
}}

QPushButton:disabled {{
    background-color: {color_disabled_bg};
    color: {color_disabled_text};
    border: 1.5px solid {color_disabled_bg};
}}

QPushButton#secondaryButton {{
    background-color: {color_surface};
    color: {color_text};
    border: 1.5px solid {color_border};
}}

QPushButton#secondaryButton:hover {{
    background-color: {color_surface_hover};
}}

QPushButton#secondaryButton:disabled {{
    background-color: {color_surface};
    color: {color_text_faint};
    border: 1.5px solid {color_text_faint};
}}

/* Chip-style toggle button (Terminal quick-sale presets, payment method,
   nozzle picker - 2026-08-25) - uses Qt's native :checked pseudo-state
   directly, no manual property-polish dance needed the way the sidebar's
   active-item highlighting requires (that one keys off which page is
   open, not a togglable button state). */
QPushButton#chip {{
    background-color: {color_surface};
    color: {color_text};
    border: 1.5px solid {color_border};
    border-radius: {RADIUS_LG}px;
    padding: 8px 14px;
    font-weight: 600;
}}

QPushButton#chip:hover {{
    background-color: {color_surface_hover};
}}

QPushButton#chip:checked {{
    background-color: {color_primary};
    color: {color_primary_text};
    border: 1.5px solid {color_primary};
}}

QWidget#topBar {{
    background-color: {color_surface};
    border-bottom: 1px solid {color_border};
}}

/* Shown above an embedded module page (2026-08-25) - lets the operator
   step back toward the dashboard without the page itself needing its
   own window chrome, now that every module lives inside MainWindow's
   own content area instead of opening as a separate top-level window. */
QWidget#breadcrumbBar {{
    background-color: {color_surface};
    border-bottom: 1px solid {color_border};
}}

QLabel#breadcrumbLabel {{
    color: {color_text_muted};
    font-size: 13px;
    font-weight: 600;
}}

QPushButton#breadcrumbLink {{
    background-color: transparent;
    border: none;
    color: {color_text};
    font-size: 13px;
    font-weight: 600;
    padding: 0;
}}

QPushButton#breadcrumbLink:hover {{
    text-decoration: underline;
}}

QLabel#breadcrumbSeparator {{
    color: {color_text_faint};
    font-size: 13px;
}}

QLabel#userLabel {{
    font-size: 14px;
    font-weight: 600;
}}

/* Pill Tag / Badge - white fill, hairline border, uppercase mono text -
   "feels like a version tag or a label sticker," not a colored fill.
   Routine identifiers like a role badge stay achromatic; color is
   reserved for genuine status meaning elsewhere (danger/success/caution). */
QLabel#roleTag {{
    background-color: {color_surface};
    color: {color_text};
    border: 1.5px solid {color_border};
    border-radius: {RADIUS_FULL}px;
    padding: 4px 10px;
    font-family: {FONT_MONO};
    font-size: 12px;
    font-weight: 700;
}}

QLabel#statusTagActive {{
    background-color: {color_success_bg};
    color: {color_success};
    border-radius: {RADIUS_FULL}px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
}}

QLabel#statusTagInactive {{
    background-color: {color_danger_bg};
    color: {color_danger};
    border-radius: {RADIUS_FULL}px;
    padding: 2px 10px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton#dangerButton {{
    background-color: {color_surface};
    color: {color_danger};
    border: 1.5px solid {color_danger};
}}

QPushButton#dangerButton:hover {{
    background-color: {color_danger_bg};
    color: {color_danger_hover};
}}

QPushButton#dangerButton:disabled {{
    background-color: {color_surface};
    color: {color_text_faint};
    border: 1.5px solid {color_text_faint};
}}

QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {color_surface};
    border: 1.5px solid {color_border};
    border-radius: {RADIUS_MD}px;
    padding: 8px 10px;
    font-size: 14px;
}}

QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {color_text};
}}

QDialog {{
    background-color: {color_bg};
}}

QTabWidget::pane {{
    background-color: {color_bg};
    border: 1px solid {color_border};
    border-radius: {RADIUS_LG}px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: transparent;
    color: {color_text_muted};
    padding: 8px 18px;
    margin-right: 4px;
    border-top-left-radius: {RADIUS_MD}px;
    border-top-right-radius: {RADIUS_MD}px;
    font-weight: 600;
}}

QTabBar::tab:selected {{
    background-color: {color_surface};
    color: {color_text};
    border: 1px solid {color_border};
    border-bottom: none;
}}

QTabBar::tab:hover:!selected {{
    color: {color_text};
}}

QTableWidget {{
    background-color: {color_surface};
    alternate-background-color: {color_surface_hover};
    border: 1px solid {color_border};
    border-radius: {RADIUS_LG}px;
    gridline-color: {color_border};
    selection-background-color: {COLOR_SELECTION_WASH};
    selection-color: {color_text};
}}

/* Plain, light table header - a border-bottom rather than a filled bar,
   uppercase muted caption text, matching the mockup's own audit/roster
   table headers exactly. Previously a permanently-dark filled bar
   regardless of theme; now theme-aware like every other surface. */
QHeaderView::section {{
    background-color: {color_surface};
    color: {color_text_muted};
    padding: 8px;
    border: none;
    border-bottom: 1.5px solid {color_border};
    font-weight: 700;
    font-size: 11px;
}}

QListWidget {{
    background-color: {color_surface};
    border: 1px solid {color_border};
    border-radius: {RADIUS_LG}px;
}}

QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 600;
    margin-top: 8px;
}}

/* --- Login hero panel ---
   A fixed dark marketing panel independent of the reference mockup (which
   has no login screen) - kept as a deliberate design choice, still fully
   consistent with the new black/white palette. */

QWidget#heroPanel {{
    background-color: {COLOR_CARBON_BLACK};
}}

QLabel#heroTitle {{
    color: {COLOR_PAPER_WHITE};
    font-size: 30px;
    font-weight: 700;
}}

QLabel#heroTagline {{
    color: {COLOR_ASH};
    font-size: 14px;
}}

QLabel#heroBullet {{
    color: {COLOR_PAPER_WHITE};
    font-size: 13px;
}}

QWidget#heroBadge {{
    background-color: {COLOR_CARBON_BLACK};
    border: 1.5px solid {COLOR_PAPER_WHITE};
    border-radius: 22px;
}}

QLabel#heroBadgeGlyph {{
    color: {COLOR_PAPER_WHITE};
    font-size: 22px;
    font-weight: 700;
}}

/* --- Login redesign (2026-08-25): feature rows with their own icon
   chip (the same icon-chip + title + description language dashCard
   already uses, restated here in the hero panel's dark-on-black
   register), plus a bottom-anchored footer bar so the panel's lower
   half carries real information (device/date) instead of empty space. */

QWidget#heroFeatureIcon {{
    background-color: {COLOR_GRAPHITE};
    border: 1px solid {COLOR_STEEL};
    border-radius: {RADIUS_LG}px;
}}

QLabel#heroFeatureIconGlyph {{
    font-size: 16px;
    qproperty-alignment: AlignCenter;
}}

QLabel#heroFeatureTitle {{
    color: {COLOR_PAPER_WHITE};
    font-size: 14px;
    font-weight: 700;
}}

QLabel#heroFeatureDesc {{
    color: {COLOR_ASH};
    font-size: 12px;
}}

QWidget#heroFooter {{
    border-top: 1px solid {COLOR_GRAPHITE};
}}

QLabel#heroFooterText {{
    color: {COLOR_STEEL};
    font-size: 11px;
    font-family: {FONT_MONO};
}}

/* --- Login form card --- */

QLabel#fieldLabel {{
    color: {color_text_muted};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

QPushButton#togglePasswordButton {{
    background-color: {color_surface};
    color: {color_text_muted};
    border: 1.5px solid {color_border};
    border-radius: {RADIUS_MD}px;
    padding: 0px 12px;
    font-size: 12px;
    font-weight: 600;
}}

QPushButton#togglePasswordButton:hover {{
    background-color: {color_surface_hover};
    color: {color_text};
}}

QLabel#loginFootnote {{
    color: {color_text_faint};
    font-size: 12px;
}}

/* --- Dashboard quick-access cards --- */

QWidget#dashCard {{
    background-color: {color_surface};
    border: 1px solid {color_border};
    border-radius: {RADIUS_XL}px;
}}

QWidget#dashCard:hover {{
    border: 1.5px solid {color_text};
}}

QLabel#dashCardIcon {{
    background-color: {color_surface_hover};
    color: {color_text};
    border-radius: {RADIUS_LG}px;
    font-size: 18px;
    font-weight: 700;
    qproperty-alignment: AlignCenter;
}}

QLabel#dashCardTitle {{
    font-size: 15px;
    font-weight: 700;
}}

QLabel#dashCardSubtitle {{
    font-size: 12px;
    color: {color_text_muted};
}}

QLabel#dashGreeting {{
    font-size: 24px;
    font-weight: 700;
}}

QLabel#dashDate {{
    font-size: 13px;
    color: {color_text_muted};
}}

QLabel#dashGroupLabel {{
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
    color: {color_text_muted};
}}

/* --- Dashboard KPI strip ---
   Plain by default - the mockup's KPI numerals are always plain bold
   black, never color-tinted; color only appears on the one tile that
   genuinely needs attention (e.g. "3 tanks running low"), as a red
   left-border + tinted background + red caption, matching the mockup's
   own "Low Stock Alert" card treatment exactly. */

QWidget#statCard {{
    background-color: {color_surface};
    border: 1px solid {color_border};
    border-radius: {RADIUS_LG}px;
}}

QWidget#statCard[tone="warning"] {{
    background-color: {color_danger_bg};
    border: 1px solid {color_border};
    border-left: 4px solid {color_danger};
}}

QLabel#statValue {{
    font-family: {FONT_MONO};
    font-size: 26px;
    font-weight: 800;
    color: {color_text};
}}

QLabel#statLabel {{
    font-size: 12px;
    color: {color_text_muted};
    font-weight: 600;
}}

QLabel#statLabel[tone="warning"] {{
    color: {color_danger};
}}

/* --- Notifications (problemstatement.md #43) ---
   Severity is carried by a `tone` property rather than three separate
   object names, so the alert widget stays one widget and Qt re-polishes
   it when the severity changes. Critical = red, warning = amber (this
   app's own three-tier severity model), plain = achromatic. */

QWidget#alertCard {{
    background-color: {color_surface};
    border: 1px solid {color_border};
    border-left: 4px solid {color_text};
    border-radius: {RADIUS_LG}px;
}}

QWidget#alertCard[tone="critical"] {{
    border-left: 4px solid {color_danger};
}}

QWidget#alertCard[tone="warning"] {{
    border-left: 4px solid {color_caution};
}}

QLabel#alertTitle {{
    font-size: 15px;
    font-weight: 700;
}}

QLabel#alertDetail {{
    font-size: 13px;
    color: {color_text_muted};
}}

/* Same Pill Tag / Badge treatment as roleTag - white fill, black
   border/text by default; tone only recolors the border+text for the
   two states that genuinely need to stand out, never a solid fill. */
QLabel#alertTag {{
    font-family: {FONT_MONO};
    font-size: 12px;
    font-weight: 700;
    border: 1.5px solid {color_border};
    border-radius: {RADIUS_FULL}px;
    padding: 4px 10px;
    background-color: {color_surface};
    color: {color_text};
}}

QLabel#alertTag[tone="critical"] {{
    border: 1.5px solid {color_danger};
    color: {color_danger};
}}

QLabel#alertTag[tone="warning"] {{
    border: 1.5px solid {color_caution};
    color: {color_caution_text};
}}

/* The top-bar button that opens the alerts screen. It carries its own
   count, so a `tone` of "critical"/"warning" makes an unattended problem
   visible from the dashboard without the operator opening anything. The
   resting state (zero alerts, or informational-only ones) stays
   achromatic - color is reserved for genuine status meaning. */
QPushButton#alertsButton {{
    background-color: {color_surface};
    color: {color_text};
    border: 1.5px solid {color_border};
    border-radius: {RADIUS_LG}px;
    padding: 8px 14px;
    font-weight: 700;
}}

QPushButton#alertsButton:hover {{
    background-color: {color_text};
    color: {color_bg};
}}

QPushButton#alertsButton[tone="critical"] {{
    background-color: {color_danger_bg};
    color: {color_danger};
    border: 1.5px solid {color_danger};
}}

QPushButton#alertsButton[tone="warning"] {{
    background-color: {color_caution_bg};
    color: {color_caution_text};
    border: 1.5px solid {color_caution};
}}

/* --- Persistent left sidebar (2026-08-24, retheme 2026-08-25) ---
   Was a permanently-dark surface regardless of app theme (matching an
   earlier client reference); the PetrolStream reference's own sidebar is
   a plain light panel nearly the same tone as the page it sits beside,
   distinguished only by a hairline border - so this is now theme-aware
   like every other surface instead of fixed. */

QWidget#sidebar {{
    background-color: {color_bg};
    border-right: 1px solid {color_border};
}}

QWidget#sidebarBrandBlock {{
    background-color: {color_bg};
    border-bottom: 1px solid {color_border};
}}

QLabel#sidebarBrandTitle {{
    color: {color_text};
    font-size: 18px;
    font-weight: 700;
}}

QLabel#sidebarBrandSubtitle {{
    color: {color_text_muted};
    font-size: 12px;
    font-family: {FONT_MONO};
}}

QWidget#sidebarScroll {{
    background-color: {color_bg};
    border: none;
}}

QLabel#sidebarGroupLabel {{
    color: {color_text_faint};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 12px 12px 4px 12px;
}}

QPushButton#sidebarNavItem {{
    background-color: transparent;
    color: {color_text_muted};
    border: none;
    border-radius: {RADIUS_MD}px;
    padding: 10px 12px;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
}}

QPushButton#sidebarNavItem:hover {{
    background-color: {color_surface_hover};
    color: {color_text};
}}

QPushButton#sidebarNavItem[active="true"] {{
    background-color: {color_surface_hover};
    color: {color_text};
    border-left: 3px solid {color_text};
    padding-left: 9px;
}}

QWidget#sidebarFooterBlock {{
    background-color: {color_bg};
    border-top: 1px solid {color_border};
}}

/* --- Tank gauge card (2026-08-24) ---
   The "empty" track behind TankGaugeCard's hand-painted fill - the fill
   itself (plain black/white for a routine reading, red for a low one,
   unchanged between themes) is drawn in Python since QSS cannot express a
   proportional fill, but the track around it is ordinary declarative QSS
   like everything else. */
QWidget#gaugeTrack {{
    background-color: {color_surface_hover};
    border: 1px solid {color_border};
    border-radius: {RADIUS_MD}px;
}}

QLabel#alertEmptyState {{
    font-size: 15px;
    color: {color_success};
    background-color: {color_success_bg};
    border: 1px solid {color_success};
    border-radius: {RADIUS_XL}px;
    padding: 24px;
}}
"""


# Default export for anything importing the light-mode stylesheet
# directly - app.ui.theme.apply_theme() is what actually picks light vs.
# dark at runtime; this stays light so it is never accidentally the
# active theme just by being imported.
STYLESHEET = build_stylesheet(dark=False)
