"""Build docs/manual/Petrol_Pump_ERP_User_Manual.pdf.

Screenshots come from scripts/capture_manual_screenshots.py (docs/manual/img).
The role-access table is generated from the real ROLE_PERMISSIONS, so it
cannot drift from what the app actually enforces.

Run with: python scripts/build_manual_pdf.py
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from app.core.constants import ROLE_PERMISSIONS, Permission, UserRole

IMG = ROOT / "docs" / "manual" / "img"
OUT = ROOT / "docs" / "manual" / "Petrol_Pump_ERP_User_Manual.pdf"
VERSION = "1.0"

FONTS = Path("C:/Windows/Fonts")
try:
    pdfmetrics.registerFont(TTFont("UI", str(FONTS / "segoeui.ttf")))
    pdfmetrics.registerFont(TTFont("UI-B", str(FONTS / "segoeuib.ttf")))
    pdfmetrics.registerFont(TTFont("UI-I", str(FONTS / "segoeuii.ttf")))
    pdfmetrics.registerFontFamily("UI", normal="UI", bold="UI-B", italic="UI-I", boldItalic="UI-B")
    BODY, BOLD = "UI", "UI-B"
except Exception:  # noqa: BLE001 - fall back to built-ins (no rupee glyph)
    BODY, BOLD = "Helvetica", "Helvetica-Bold"

INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#555555")
ACCENT = colors.HexColor("#0B5FFF")
LINE = colors.HexColor("#D9D9D9")
TIP_BG, WARN_BG, RULE_BG = colors.HexColor("#EAF3FF"), colors.HexColor("#FFF4D6"), colors.HexColor("#EAF7EE")

S = {
    "body": ParagraphStyle("body", fontName=BODY, fontSize=10, leading=14.5, textColor=INK, spaceAfter=5),
    "h1": ParagraphStyle("h1", fontName=BOLD, fontSize=22, leading=26, textColor=INK, spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=14.5, leading=18, textColor=INK, spaceBefore=12, spaceAfter=5, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName=BOLD, fontSize=11, leading=14, textColor=ACCENT, spaceBefore=8, spaceAfter=3, keepWithNext=1),
    "bullet": ParagraphStyle("bullet", fontName=BODY, fontSize=10, leading=14, textColor=INK, leftIndent=14,
                             bulletIndent=3, spaceAfter=2),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=8.6, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName=BOLD, fontSize=8.6, leading=11, textColor=INK),
    "cap": ParagraphStyle("cap", fontName=BODY, fontSize=8, leading=10, textColor=MUTED, alignment=TA_CENTER,
                          spaceAfter=8),
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=34, leading=40, textColor=INK, alignment=TA_CENTER),
    "sub": ParagraphStyle("sub", fontName=BODY, fontSize=14, leading=19, textColor=MUTED, alignment=TA_CENTER),
}
S["toc1"] = ParagraphStyle("toc1", fontName=BOLD, fontSize=11, leading=17, textColor=INK, spaceBefore=4)
S["toc2"] = ParagraphStyle("toc2", fontName=BODY, fontSize=9.5, leading=13, leftIndent=14, textColor=MUTED)

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


class Manual(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(str(path), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=20 * mm,
                         bottomMargin=18 * mm, title="Petrol Pump ERP - User Manual", author="Petrol Pump ERP")
        frame = Frame(MARGIN, 18 * mm, CONTENT_W, PAGE_H - 38 * mm, id="f", leftPadding=0, rightPadding=0,
                      topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=self._decorate)])

    def _decorate(self, canv, doc):
        if doc.page == 1:
            return
        canv.saveState()
        canv.setFont(BODY, 8)
        canv.setFillColor(MUTED)
        canv.drawString(MARGIN, PAGE_H - 12 * mm, "Petrol Pump ERP - User Manual")
        canv.drawRightString(PAGE_W - MARGIN, PAGE_H - 12 * mm, f"Version {VERSION}")
        canv.setStrokeColor(LINE)
        canv.line(MARGIN, PAGE_H - 14 * mm, PAGE_W - MARGIN, PAGE_H - 14 * mm)
        canv.drawCentredString(PAGE_W / 2, 10 * mm, f"Page {doc.page}")
        canv.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ("h1", "h2"):
            level = 0 if flowable.style.name == "h1" else 1
            text = flowable.getPlainText()
            key = f"t{self.seq.nextf('toc')}"
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (level, text, self.page, key))


story: list = []


def P(text, style="body"):
    story.append(Paragraph(text, S[style]))


def H1(text):
    story.append(PageBreak())
    P(text, "h1")


def H2(text):
    P(text, "h2")


def H3(text):
    P(text, "h3")


def B(*items):
    for item in items:
        story.append(Paragraph(item, S["bullet"], bulletText="•"))


def N(*items):
    for i, item in enumerate(items, 1):
        story.append(Paragraph(item, S["bullet"], bulletText=f"{i}."))


def box(label, text, bg):
    t = Table([[Paragraph(f"<b>{label}</b> {text}", S["cell"])]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(t)
    story.append(Spacer(1, 6))


def TIP(text):
    box("Tip:", text, TIP_BG)


def WARN(text):
    box("Important:", text, WARN_BG)


def RULE(text):
    box("Rule:", text, RULE_BG)


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), S["cellb"] if (header and r == 0) else S["cell"]) for c in row]
            for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * CONTENT_W for w in widths], repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F0F0")))
    t.setStyle(TableStyle(style))
    story.append(t)
    story.append(Spacer(1, 8))


def shot(slug, caption):
    path = IMG / f"{slug}.png"
    if not path.exists():
        raise SystemExit(f"missing screenshot {path} - run scripts/capture_manual_screenshots.py")
    from PIL import Image as PILImage
    w, h = PILImage.open(path).size
    width = CONTENT_W
    height = width * h / w
    img = Image(str(path), width=width, height=height)
    img.hAlign = "CENTER"
    t = Table([[img]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether([t, Spacer(1, 2), Paragraph(caption, S["cap"])]))


def screen(slug, title, purpose, who, buttons, steps=None, notes=None, rules=None):
    """One chapter-section per screen: picture, purpose, who, controls, steps, notes."""
    H2(title)
    P(purpose)
    shot(slug, f"{title} screen (sample demo data)")
    P(f"<b>Who can open it:</b> {who}")
    if buttons:
        H3("What's on the screen")
        table([["Control", "What it does"]] + [[a, b] for a, b in buttons], [0.28, 0.72])
    if steps:
        H3("How to do the common tasks")
        for name, items in steps:
            P(f"<b>{name}</b>")
            N(*items)
    if rules:
        for r in rules:
            RULE(r)
    if notes:
        for n in notes:
            TIP(n)


# --------------------------------------------------------------------------
# Role access table (generated from the app's real permission map)
# --------------------------------------------------------------------------
TILE_PERMISSIONS = [
    ("Employees", "EMPLOYEE_VIEW"), ("Users", "USER_MANAGE"), ("Fuel Prices", "FUEL_PRICE_VIEW"),
    ("Tanks", "INVENTORY_VIEW"), ("Nozzles & Dispensers", "NOZZLE_VIEW"), ("Suppliers", "PROCUREMENT_VIEW"),
    ("Company Profile", "SETTINGS_VIEW"), ("Terminal", "SALE_MANAGE"), ("Sales", "SALE_VIEW"),
    ("Shifts", "SHIFT_VIEW"), ("My Shift", "MY_ASSIGNMENT_VIEW"), ("Attendance", "ATTENDANCE_VIEW"),
    ("Leave", "LEAVE_VIEW"), ("Credit", "CREDIT_VIEW"), ("Expenses", "EXPENSE_VIEW"),
    ("Reconciliation", "RECONCILIATION_VIEW"), ("Procurement", "PROCUREMENT_VIEW"),
    ("Reports: Sales / Payments / Daily / Attendant", "SALE_VIEW"),
    ("Reports: Fuel Summary / Fuel Movement", "INVENTORY_VIEW"),
    ("Reports: Expenses / Cash Book", "EXPENSE_VIEW"), ("Reports: Credit", "CREDIT_VIEW"),
    ("Reports: Reconciliation", "RECONCILIATION_VIEW"), ("Reports: Attendance", "ATTENDANCE_VIEW"),
    ("Reports: Business Insights", "ANALYTICS_VIEW"), ("Backups", "BACKUP_MANAGE"), ("Audit Log", "AUDIT_VIEW"),
]
ROLE_ORDER = [UserRole.ADMIN, UserRole.OWNER, UserRole.MANAGER, UserRole.ACCOUNTANT, UserRole.SHIFT_SUPERVISOR,
              UserRole.ATTENDANT]


def role_table():
    header = ["Screen"] + ["Admin", "Owner", "Manager", "Accountant", "Supervisor", "Attendant"]
    rows = [header]
    for label, perm_name in TILE_PERMISSIONS:
        perm = Permission[perm_name]
        rows.append([label] + ["Yes" if perm in ROLE_PERMISSIONS[r] else "-" for r in ROLE_ORDER])
    table(rows, [0.34] + [0.11] * 6)


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------
def cover():
    story.append(Spacer(1, 55 * mm))
    P("Petrol Pump ERP", "title")
    story.append(Spacer(1, 6 * mm))
    P("Complete User Manual", "sub")
    story.append(Spacer(1, 4 * mm))
    P("Installation, daily operation, every screen, reports, backups and recovery", "sub")
    story.append(Spacer(1, 30 * mm))
    P(f"Version {VERSION} &nbsp;|&nbsp; {date.today():%d %B %Y}", "sub")
    story.append(Spacer(1, 6 * mm))
    P("Works fully offline - no internet, account or server needed", "sub")
    story.append(PageBreak())
    story.append(Paragraph("Contents", ParagraphStyle("ctitle", parent=S["h1"])))
    toc = TableOfContents()
    toc.levelStyles = [S["toc1"], S["toc2"]]
    story.append(toc)


def part_intro():
    H1("1. About this manual")
    P("Petrol Pump ERP runs a petrol pump from one Windows PC: staff, fuel prices, tanks and nozzles, shifts, "
      "sales, credit customers, expenses, purchases from suppliers, cash and fuel reconciliation, reports and "
      "backups. It works entirely offline. Your data stays on the computer it is installed on.")
    P("This manual explains the application screen by screen. You do not need any technical knowledge. Read "
      "chapters 2 to 4 first, then jump to the screens that apply to your job.")
    H2("Who should read what")
    table([["If you are...", "Read these chapters"],
           ["Setting the system up for the first time", "2 Installation, 5 First-day setup, 6 Masters, 11 Backups"],
           ["An attendant at the counter", "3 Getting around, 7 Terminal, 7 My Shift, 13 Daily routine"],
           ["A shift supervisor", "7 Shifts, Attendance, Reconciliation, 13 Daily routine"],
           ["A manager or owner", "Everything - especially 7 Operations, 8 Reports, 12 Alerts"],
           ["An accountant", "7 Credit, Expenses, Reconciliation, 8 Reports"],
           ["The administrator", "2 Installation, 6 Users, 11 Backups & Audit Log, 14 Security"]],
          [0.38, 0.62])
    H2("The pictures in this manual")
    P("Every screenshot was taken from the real application filled with <b>demo data</b> (about ten weeks of "
      "made-up shifts, sales and customers). The names, amounts and alerts you see in the pictures are not "
      "real. Your own screens will show your own data, and a brand-new installation starts almost empty.")
    H2("Words used in this manual")
    table([["Word", "Meaning"],
           ["Click", "Press the left mouse button on a button or item."],
           ["Tile", "A card on a menu page that opens one screen (for example 'Employees')."],
           ["Shift", "A working period at the pump (for example 'Morning' on one date)."],
           ["Nozzle", "One fuel gun on a dispenser. Each dispenser has exactly two nozzles."],
           ["Reconciliation", "Comparing what the system expected (cash, UPI, card, fuel) with what was actually counted."],
           ["Void / Reverse / Adjust", "How mistakes are corrected. Records are never deleted - see chapter 4."]],
          [0.22, 0.78])


def part_install():
    H1("2. Installing and signing in")
    H2("Option A - the installer (recommended, Windows)")
    N("On any computer with internet, open <b>https://github.com/Rahil-Mokashi/initial-capstone/releases</b> "
      "and open the newest release at the top.",
      "Under <b>Assets</b>, download <b>PetrolPumpERP-Setup-1.0.0.exe</b> (the installer). If you prefer not to "
      "install, download <b>PetrolPumpERP.exe</b> instead - it is one portable file you can double-click.",
      "Copy the file to the pump PC (a USB stick is fine - the pump PC itself never needs internet).",
      "Double-click the file. The installer needs no administrator rights. Click through the prompts. "
      "It adds a Start Menu shortcut for the app and for this documentation.",
      "Open <b>Petrol Pump ERP</b> from the Start Menu.")
    WARN("If Windows shows a blue 'Windows protected your PC' screen, click <b>More info</b>, then <b>Run "
         "anyway</b>. This appears because the program is new and not yet signed with a paid publisher "
         "certificate. It does not mean the file is damaged.")
    H2("Option B - run from source (technical users, any OS)")
    P("Install <b>Python 3.13+</b> (on Windows tick 'Add python.exe to PATH') and <b>Git</b>, then in a terminal:")
    story.append(Paragraph(
        "git clone https://github.com/Rahil-Mokashi/initial-capstone.git<br/>cd initial-capstone<br/>"
        "python -m venv venv<br/>venv\\Scripts\\activate &nbsp;&nbsp;(macOS/Linux: source venv/bin/activate)<br/>"
        "pip install -r requirements.txt<br/>python -m app.main",
        ParagraphStyle("code", parent=S["body"], fontName="Courier", fontSize=8.8, leading=12,
                       backColor=colors.HexColor("#F4F4F4"), borderPadding=6, spaceAfter=10)))
    P("Optional: <b>python scripts/seed_demo_data.py</b> loads ten weeks of demo data so you can explore "
      "every report. Never run it on a pump's real database.")
    H2("Your first sign-in")
    shot("login", "The login screen")
    N("Type the username <b>admin</b> and the password <b>Admin@123</b>.",
      "The app immediately asks you to choose a <b>new password</b>. This cannot be skipped, because the default "
      "password is publicly known. Use at least 8 characters with an uppercase letter, a lowercase letter and a digit.",
      "<b>Write the new password down and keep it somewhere safe.</b> Only another administrator account can "
      "reset it.",
      "Open <b>Masters -> Users</b> and create a personal account for every person who needs one. Stop using the "
      "shared 'admin' login for daily work, so the audit trail shows who really did what.")
    H3("Login screen extras")
    B("<b>Wrong password 5 times</b> locks the account. It unlocks itself after 15 minutes, or an administrator "
      "can unlock it straight away (Users screen).",
      "<b>Forgot password:</b> use the forgot-password link on the login screen. An administrator can generate a "
      "one-time reset code for you (Users screen -> Generate Password Reset Code).",
      "<b>PIN sign-in</b> (optional): counter staff can set a short PIN from the sidebar (Change Password area) for "
      "quick sign-in and for unlocking the screen.",
      "<b>Windows Hello</b> (optional, needs an extra component): fingerprint/face unlock of the lock screen.",
      "A <b>Caps Lock</b> warning appears while typing the password; a language toggle switches English / regional.",
      "Sessions end automatically after inactivity (8 hours by default). Nothing in progress is lost - sales are "
      "saved as you go.")
    H2("Where your data lives")
    P("Everything is stored on the PC, per Windows user, in <b>%LOCALAPPDATA%\\PetrolPumpERP\\</b>:")
    table([["Item", "What it is"],
           ["petrol_pump.db", "The database - every sale, employee, shift and balance."],
           ["backups\\", "Database backups (automatic and manual)."],
           ["reports\\", "Default folder for exported PDFs, Excel files and receipts."],
           ["petrol_pump_erp.log", "A plain-text log used to diagnose problems."],
           ["config.env", "Optional settings file (see Appendix A)."]],
          [0.28, 0.72])
    P("Uninstalling the program never deletes this folder. To move to a new PC, copy a backup file across and "
      "restore it (chapter 11).")
    H2("Installing on several computers")
    P("Each PC is completely independent: it has its own database. There is no network sync by design. If two "
      "counters must share one set of records, use one PC as the pump's main computer. Repeat the steps above on "
      "every PC where the app should run, and set each up separately.")


def part_navigation():
    H1("3. Getting around the app")
    shot("dashboard", "Dashboard after sign-in")
    H2("The window layout")
    table([["Area", "What it shows or does"],
           ["Sidebar (left)", "Four groups - <b>Masters</b>, <b>Operations</b>, <b>Reports</b>, <b>Settings</b> - plus "
            "Dashboard. At the bottom: <b>Support</b>, <b>Change Password</b>, <b>Lock</b>, <b>Logout</b>. A group "
            "only appears if your role can open something inside it."],
           ["Search box (top)", "Searches employees, nozzles, tanks and (for administrators) user accounts. Press "
            "<b>Ctrl+F</b> to jump into it. You only ever find records your role may see."],
           ["Offline badge", "Green 'Offline - Local Only' - a reminder that the app never uses the internet."],
           ["Shift indicator", "Shows whether a shift is open on this pump right now, and which one."],
           ["Clock", "Date and time of the PC."],
           ["Alerts button", "A count of things needing attention. Click it for the list. See chapter 12."],
           ["Your name menu", "Your account: change password, set PIN, lock, sign out."],
           ["Alert strip", "A coloured banner under the top bar, visible on every screen, summarising the most urgent "
            "alert. Click it to open the exact screen the alert is about."],
           ["Back button & trail", "Under the strip: <b>Back</b> returns one level; the trail shows where you are."]],
          [0.22, 0.78])
    H2("Keyboard shortcuts")
    table([["Keys", "Action"],
           ["Ctrl+F", "Jump to the search box"],
           ["F5", "Refresh the screen you are on"],
           ["Esc", "Go back one level"]],
          [0.2, 0.8])
    H2("The four menus")
    P("Clicking <b>Masters</b>, <b>Operations</b>, <b>Reports</b> or <b>Settings</b> opens a menu page of tiles, "
      "grouped under headings, each with a one-line description. Click a tile to open that screen.")
    shot("landing-masters", "Masters menu - the 'set up once, change rarely' information")
    shot("landing-operations", "Operations menu - the daily work")
    shot("landing-settings", "Settings menu - backups and the audit log")
    shot("landing-reports", "Reports menu - every report you may open")
    H2("The dashboard")
    P("The dashboard is a live snapshot of the pump: <b>sales today</b>, <b>revenue today</b>, <b>shifts open "
      "now</b>, <b>tanks running low</b>, <b>purchase orders pending</b>, then <b>Live tank levels</b> (a gauge per "
      "tank), a sales chart, who is on shift, and an <b>Attention needed</b> list. Every figure is shown only "
      "if your role is allowed to see it.")
    H2("What a restricted role sees")
    P("An attendant, for example, sees a much smaller menu - their own shift, the sales terminal, and little else.")
    shot("attendant-dashboard", "Dashboard as an attendant")
    TIP("If a screen or button you expect is missing, it is a permission setting, not a fault. Ask your administrator "
        "rather than trying to work around it.")


def part_roles():
    H1("4. Roles, permissions and the golden rules")
    H2("Roles")
    table([["Role", "Typical person", "In one line"],
           ["Admin", "System administrator", "Everything, including users and configuration"],
           ["Owner", "Pump owner", "Everything, same practical scope as Admin"],
           ["Manager", "Pump manager", "Runs operations: staff, procurement, expenses, reports, approvals"],
           ["Accountant", "Accounts clerk", "Payments, credit, expenses, financial reports"],
           ["Shift Supervisor", "Shift in-charge", "Opens/closes shifts, assigns nozzles, reconciliation"],
           ["Attendant", "Pump attendant", "Records sales on their own nozzle; sees their own shift"]],
          [0.2, 0.25, 0.55])
    H2("Who can open which screen")
    P("This table is generated from the application's own permission settings, so it is exactly what the app "
      "enforces. 'Yes' means the role can open that screen.")
    role_table()
    H2("The golden rules")
    RULE("<b>Nothing is ever deleted or silently overwritten.</b> Mistakes are fixed with a visible correcting "
         "action - void, cancel, reverse, adjust or reject - and almost always require a written <b>reason</b>. The "
         "original, the correction and the reason all stay on record.")
    RULE("<b>Never fix a number by re-entering data.</b> Re-entering creates a duplicate and makes the books "
         "untrustworthy. Use the correction action on the original record (for example Cancel Selected on a sale).")
    RULE("<b>A variance is not an accusation.</b> Differences between expected and counted money or fuel are "
         "recorded and graded (Normal, Warning, Investigation Required, Approval Required). Small ones are normal.")
    RULE("<b>Every important action is audited:</b> who, what, when, and the old and new values. The Audit Log "
         "screen shows them and cannot be edited.")
    RULE("<b>Prices are locked at the moment of sale.</b> Changing a fuel's price later never changes a sale "
         "already made.")
    RULE("<b>Closed means closed.</b> A closed shift or a decided request (approved/rejected) is final. "
         "Reopening a shift needs a stricter permission and a reason.")


def part_setup():
    H1("5. First-day setup checklist")
    P("Do these in order. Several steps are blocked until an earlier one is done - this is deliberate: the system "
      "refuses to record data it knows is wrong. Allow about an hour.")
    N("<b>Sign in and change the admin password</b> (chapter 2).",
      "<b>Company Profile</b> (Masters -> System): enter the company name, address and GSTIN. They are printed on "
      "receipts and reports.",
      "<b>Fuel Prices</b>: set a real selling rate for Petrol, Diesel and Power. They start at 0.00 and the app "
      "<b>refuses to record any sale</b> of an unpriced fuel.",
      "<b>Tanks</b>: create each tank with its fuel type, capacity and the <b>real current stock</b> (dip the tank "
      "and enter the measured figure). Every future reconciliation measures against this opening number.",
      "<b>Nozzles & Dispensers</b>: add each dispenser, then its two nozzles. If a fuel has more than one tank, "
      "choose which tank each nozzle draws from.",
      "<b>Employees</b>: add everyone working at the pump.",
      "<b>Users</b>: create a login for each person who needs one, with their role. Never share logins.",
      "<b>Credit customers</b> (Operations -> Sales -> Customers, then Operations -> Credit): create the customer, "
      "then open a credit account with a limit and payment terms. Both steps are required before credit sales are "
      "possible. Record any amount a customer already owes as an opening credit sale.",
      "<b>Suppliers</b>: add your fuel suppliers.",
      "<b>Backups</b>: take a manual backup, then use <b>Copy to USB / Network</b> to put a copy off the machine.")
    WARN("Do not skip the fuel prices. If sales are refused with a price message, this is the reason.")


def part_masters():
    H1("6. Masters - the set-up information")
    P("Masters holds information you set up once and change rarely. Open it from the sidebar.")
    screen("page-employees", "Employees",
           "Staff records. An employee record is separate from a login account: you can keep HR records for people who "
           "never sign in. Codes are generated automatically (EMP-0001, EMP-0002 ...).",
           "Roles with Employee View permission (Admin, Owner, Manager and others - see the table in chapter 4).",
           [("Search box", "Find by name or employee code."),
            ("+ Add Employee", "Opens the new-employee form."),
            ("Status drop-down (in each row)", "Change an employee between active, on leave, suspended or terminated. "
             "A reason is mandatory and the change is audited."),
            ("Pencil icon (end of row)", "Opens the employee's detail: profile, documents, and recording an exit.")],
           steps=[("Add an employee", ["Click <b>+ Add Employee</b>.", "Fill in name, designation, department, "
                                      "joining date and contact details.", "Click <b>Save</b>."]),
                  ("Attach documents (ID proof etc.)", ["Open the employee with the pencil icon.",
                                                         "Click <b>Add Document</b>, fill in the details.",
                                                         "To remove one, select it and click <b>Remove Selected</b> "
                                                         "(it is hidden, not erased)."]),
                  ("Record someone leaving", ["Open the employee, click <b>Record Exit</b>, enter the exit date and "
                                              "reason. The record stays forever."])],
           rules=["An employee is never deleted. Only the status changes, and every change is logged."])
    screen("page-users", "Users",
           "Login accounts. Several users can share one role (for example four attendants).",
           "Admin and Owner only.",
           [("+ Add User", "Create a login: username, name, role and a temporary password."),
            ("Change Role", "Move a user to a different role (reason required)."),
            ("Reset Password", "Set a new temporary password. The user must change it at next sign-in."),
            ("Unlock Account", "Clear a lockout straight away instead of waiting 15 minutes."),
            ("Generate Password Reset Code", "Creates a one-time code a user can use on the login screen's "
             "forgot-password flow."),
            ("Activate / deactivate", "Switch an account off without deleting it (reason required).")],
           steps=[("Create a login", ["Click <b>+ Add User</b>.", "Enter the details and choose the role.",
                                      "Set a temporary password that meets the policy (8+ characters, upper, lower, "
                                      "digit).", "Click <b>Save</b> and tell the person their temporary password."])],
           rules=["Accounts are never deleted. Deactivate instead - the history keeps pointing to the right person."])
    screen("page-fuel-prices", "Fuel Prices",
           "The selling rate of each fuel. Prices are versioned: every change records who made it and when.",
           "Roles with Fuel Price View; setting prices needs the matching manage permission.",
           [("Pencil icon (end of row)", "Set or change that fuel's price."),
            ("Price History", "Every past price for that fuel, newest first."),
            ("Refresh", "Reload the page.")],
           notes=["You can change a price in the middle of a shift (for example when the depot price moves). Sales "
                  "made earlier keep the price they were sold at."])
    screen("page-tanks", "Tanks",
           "Underground storage tanks and their stock. A pump may have several tanks per fuel. Stock changes only "
           "through recorded transactions.",
           "Roles with Inventory View.",
           [("+ Add Tank", "Register a tank: code, fuel, capacity, opening stock."),
            ("Change Status", "Mark a tank active, inactive, etc. (reason required)."),
            ("Record Reading", "Save a dipstick measurement. A reading is an observation - it does not change the "
             "book stock by itself."),
            ("Receipt / Issue / Adjustment", "Record fuel arriving, leaving, or a correction (an adjustment always "
             "needs a reason)."),
            ("Reconcile", "Compare expected closing stock (opening + received - sold) with the physical reading."),
            ("Tabs: Readings, Transactions, Reconciliation", "The history of each.")],
           rules=["The system rejects stock above capacity, below zero, or an adjustment with no reason."],
           notes=["Fuel reconciliation grades the difference: Normal, Warning, Investigation Required, Approval "
                  "Required. It never assumes theft; an accepted reconciliation becomes the new baseline."])
    screen("page-nozzles-dispensers", "Nozzles & Dispensers",
           "The physical pumps. Each dispenser has exactly two nozzles, and each nozzle sells one fuel.",
           "Roles with Nozzle View.",
           [("+ Add Dispenser", "Register a dispenser."),
            ("+ Add Nozzle", "Add a nozzle to an active dispenser and choose its fuel and tank."),
            ("Tabs: Dispensers / Nozzles", "Switch between the two lists."),
            ("Status change", "Active, inactive or maintenance (reason required).")],
           rules=["A third nozzle on one dispenser is refused. A nozzle currently assigned in an open shift cannot be "
                  "deactivated."])
    screen("page-suppliers", "Suppliers",
           "Fuel suppliers you buy from, and what has been ordered from each.",
           "Roles with Procurement View.",
           [("+ Add Supplier", "Create a supplier (name, contact, address)."),
            ("Deactivate", "Retire a supplier without deleting history.")])
    screen("page-company-profile", "Company Profile",
           "The business name, address and GSTIN printed on receipts and reports.",
           "Roles with Settings View.",
           [("Fields", "Company name, address, GSTIN and the default folder for exports."),
            ("Browse...", "Choose a folder."),
            ("Save Settings / Discard Changes", "Keep or throw away your edits.")])


def part_operations():
    H1("7. Operations - the daily work")
    screen("page-terminal", "Terminal (fast sale entry)",
           "The quick screen used at the counter during a live shift: pick the nozzle, enter an amount or litres, "
           "choose how the customer pays.",
           "Roles allowed to record sales (Attendant, Supervisor, Manager, Admin, Owner).",
           [("Shift", "The open shift. You can only sell during an open shift."),
            ("Attendant", "Who is serving. Attendants see only their own assignment, filled in automatically."),
            ("Nozzle buttons", "Tap the nozzle the fuel came from (N1 Petrol, N2 Diesel ...)."),
            ("Amount / Liters", "Switch between entering money or litres. The other is calculated for you."),
            ("Quick amounts", "One-tap amounts (200, 500, 1000, 2000)."),
            ("Volume and Total", "Live preview of litres and money at today's price."),
            ("Payment method", "Cash, UPI, Card or Credit.")],
           steps=[("Record a cash sale", ["Check the shift and attendant at the top.", "Tap the nozzle.",
                                         "Tap a quick amount or type an amount.", "Choose <b>Cash</b>.",
                                         "Confirm to record the sale."]),
                  ("UPI or card", ["Choose <b>UPI</b> or <b>Card</b>.", "Fill in the UPI reference or card "
                                   "authorisation code - this makes reconciliation much easier."]),
                  ("Credit sale", ["Choose <b>Credit</b>, then select the customer.",
                                   "The sale is refused if the customer has no credit account or it would exceed the "
                                   "limit."])],
           rules=["A sale cannot be recorded until the fuel has a price and you are assigned to a nozzle in an open shift."])
    screen("page-sales", "Sales",
           "Look up past sales, manage customers, print receipts, and correct mistakes.",
           "Roles with Sale View.",
           [("Tabs: Sales / Customers", "Sales list or the customer records."),
            ("+ Record Sale", "Full sale form (managers/supervisors pick shift, nozzle and employee)."),
            ("Previous / Next", "Page through older sales."),
            ("Print Receipt / Export Receipt PDF", "A printable receipt for the selected sale."),
            ("Cancel Selected", "Cancels a completed sale: needs a reason, returns fuel to the tank and reverses the "
             "payment. The original stays on record."),
            ("Mark Payment Failed / Refund Payment", "After-the-fact payment corrections (reason required)."),
            ("+ Add Customer", "Create a customer (name, contact, address).")],
           rules=["Never delete or retype a wrong sale. Cancel it with a reason."])
    screen("page-shifts", "Shifts",
           "A shift is one working period, for example 'Morning' on one date. There can be only one shift per "
           "date and label.",
           "Roles with Shift View; opening/closing needs the shift-manage permission.",
           [("+ Open Shift", "Start a new shift (date and label)."),
            ("Open (row)", "View a shift, its assigned nozzles and attendants."),
            ("Assign Nozzle", "Assign an attendant to a nozzle with the opening meter reading."),
            ("Close Shift", "End the shift once every nozzle assignment is completed."),
            ("Reopen Shift", "Controlled correction: needs a reason and a stricter permission.")],
           steps=[("Run a shift", ["A supervisor clicks <b>+ Open Shift</b>.",
                                   "For each attendant: <b>Assign Nozzle</b>, choose the person and nozzle, enter the "
                                   "<b>opening meter reading</b> from the dispenser.",
                                   "At the end enter each <b>closing meter reading</b> (it must be at least the "
                                   "opening reading) to complete the assignment.",
                                   "Click <b>Close Shift</b>.", "Then run <b>Reconciliation</b>."])],
           rules=["The same employee cannot be assigned twice, and the same nozzle cannot go to two people in one "
                  "shift. A shift cannot be closed while any assignment is still active."])
    screen("page-my-shift", "My Shift",
           "A self-service page for attendants showing their own current nozzle, fuel, dispenser and opening meter "
           "reading.",
           "Attendants (and anyone with the My Assignment permission).",
           [("Assignment details", "Read-only. If it says no assignment, ask your supervisor to assign you.")])
    screen("page-attendance", "Attendance",
           "A daily roster of who was present, absent, late, half-day, on leave or on holiday.",
           "Roles with Attendance View; marking needs Attendance Manage.",
           [("Date filter", "Choose the day to view."),
            ("+ Mark Attendance", "Record a status, check-in/out times and overtime."),
            ("Present / Absent", "Quick buttons in the form."),
            ("Save Correction", "Change an already-marked record - needs a reason.")],
           rules=["One record per employee per day - marking twice is rejected. Corrections are audited with the "
                  "old and new values, never silently overwritten."])
    screen("page-leave", "Leave",
           "Request, approve or reject leave on an employee's behalf.",
           "Roles with Leave View; approving is a stricter, Manager-level permission.",
           [("+ Request Leave", "Create a request for an employee and date range."),
            ("Approve Selected / Reject Selected", "Decide a pending request."),
            ("Cancel Selected", "Withdraw a pending request.")],
           rules=["Approving leave automatically marks the employee's attendance as 'leave' for those dates. "
                  "Approved, rejected and cancelled requests are final. A person who submitted a request cannot "
                  "also approve it unless their role allows both."])
    screen("page-credit", "Credit",
           "Credit accounts for regular customers who buy now and pay later.",
           "Roles with Credit View.",
           [("+ Open Credit Account", "Give a customer a credit limit and payment-due days."),
            ("Change Limit", "Raise or lower the limit."),
            ("Record Payment", "Record money received from the customer."),
            ("View Statement", "Every credit sale and payment with a running balance - printable, PDF and Excel."),
            ("Overdue column", "Yes when the oldest unpaid sale is older than the due days.")],
           rules=["The balance is always calculated (credit sales minus payments), never typed. A sale that would "
                  "exceed the limit is refused, not just warned. Customer payments are never edited - a "
                  "correction is a new record."])
    screen("page-expenses", "Expenses",
           "Pump running costs, with an approval step.",
           "Roles with Expense View; approving is a stricter permission (not given to Accountants).",
           [("Tabs: Expenses / Categories", "The expense list or the category list."),
            ("+ Add Category", "Create a category such as Electricity or Repairs."),
            ("+ Record Expense", "Amount, date, employee, optional shift, payment method (cash/UPI/card), receipt "
             "reference and description."),
            ("Approve Selected / Reject Selected", "Decide a pending expense. Rejecting needs a reason.")],
           rules=["Once approved or rejected an expense is never edited or deleted. Only approved expenses count in "
                  "reconciliation."])
    screen("page-reconciliation", "Reconciliation",
           "Per-shift check of cash, UPI and card against what the system expected, plus cash custody and staff "
           "shortages.",
           "Roles with Reconciliation View; supervisors may reconcile, but only Manager and above approve "
           "high-variance results.",
           [("+ Reconcile Shift", "Enter what you actually counted (cash) and read (UPI, card) for a shift."),
            ("Approve Selected", "A manager approves a flagged reconciliation."),
            ("Variance by Tender", "Difference for Cash, Card and Other. Classification shows how serious it is."),
            ("Shift Cash Custody", "Record bank deposits and cash movements (advance/final) for the shift."),
            ("Employee Cash Shortages", "Book a named employee's shortage as a receivable and record recoveries "
             "(Manager and above).")],
           steps=[("Reconcile a shift", ["Close the shift first.", "Click <b>+ Reconcile Shift</b>.",
                                         "Enter the counted cash and the UPI and card totals.",
                                         "Save. The system compares them with its expected totals.",
                                         "If flagged for approval, a manager reviews and clicks <b>Approve "
                                         "Selected</b>."])],
           rules=["A shift is reconciled only once. Expected totals are calculated from recorded sales, payments "
                  "and approved expenses - never typed."])
    screen("page-procurement", "Procurement",
           "The full tanker-to-tank purchasing workflow.",
           "Roles with Procurement View.",
           [("Tabs: Purchase Orders / Invoices (and suppliers)", "The order list and the supplier invoices."),
            ("+ Create Purchase Order", "Order fuel from a supplier (+ Add Item per fuel)."),
            ("Record Delivery Arrival", "A tanker has arrived."),
            ("Verify Documents / Verify Quality", "Check the paperwork and the fuel quality."),
            ("Record Pre-Dip Reading", "Measure the tank before unloading."),
            ("Record Post-Dip & Unload", "Measure after unloading. Litres received = post-dip minus pre-dip, "
             "calculated for you."),
            ("Reject Delivery / Cancel Order", "Refuse a bad delivery or cancel an order."),
            ("+ Record Invoice / Record Payment", "Record the supplier's bill and pay it, fully or in part.")],
           steps=[("Receive a tanker", ["Open the purchase order, click <b>Record Delivery Arrival</b>.",
                                        "<b>Verify Documents</b>, then <b>Verify Quality</b>.",
                                        "<b>Record Pre-Dip Reading</b> on the tank.",
                                        "Unload, then <b>Record Post-Dip & Unload</b>.",
                                        "The tank's stock updates automatically.",
                                        "Later: <b>+ Record Invoice</b> and <b>Record Payment</b>."])],
           rules=["A payment cannot exceed the outstanding balance, and a fully paid invoice cannot be paid again."])


REPORTS = [
    ("report-fuel-type-summary", "Fuel Type Summary", "Per fuel (Petrol, Diesel, Power): tank count, total "
     "capacity, current stock, nozzles and the latest reconciliation variance."),
    ("report-sales-report", "Sales Report", "Every sale with fuel, amount and payment method. Date filter."),
    ("report-payment-summary-report", "Payment Summary Report", "Totals by payment method (cash, UPI, card, credit) "
     "and by payment status. Date filter."),
    ("report-expense-summary-report", "Expense Summary Report", "Expenses by category and status. Date filter."),
    ("report-credit-report-by-fuel-type", "Credit Report by Fuel Type", "Credit extended per fuel. 'Collected' and "
     "'outstanding' are shown only for the whole portfolio, because customer payments are not matched to "
     "individual sales."),
    ("report-customer-outstanding-report", "Customer Outstanding Report", "Each credit customer's balance and "
     "overdue status."),
    ("report-shift-reconciliation-report", "Shift Reconciliation Report", "Every reconciliation with variance and "
     "classification. Date filter."),
    ("report-daily-summary-report", "Daily Summary Report", "One line per trading day: sales, litres, cash, UPI, "
     "card, credit, approved expenses and what is left. Date filter."),
    ("report-attendant-nozzle-report", "Attendant & Nozzle Report", "Sales by who served and which nozzle. Filters: "
     "date, employee, nozzle. A record of what happened, not a staff ranking."),
    ("report-fuel-movement-report", "Fuel Movement Report", "Every litre in and out of each tank. Receipts, issues "
     "and adjustments are separate on purpose - a large adjustment is the figure worth asking about."),
    ("report-cash-book", "Cash Book", "Money in and out per day with a running balance. Credit sales appear when "
     "the customer pays, not on the sale day."),
    ("report-attendance-report", "Attendance Report", "Days present, absent, late, half-day and on leave per "
     "employee, with overtime. Filters: date, employee."),
    ("report-business-insights", "Business Insights (Performance & Forecast)", "Performance tab: revenue, quantity "
     "and estimated profit per fuel for a day, week, month, quarter or year (profit uses weighted-average cost and "
     "shows N/A when there is no purchase history). Sales Forecast tab: next week's expected sales per fuel from "
     "recent trends, classified as likely hike, possible dip or stable, with the reasoning shown."),
]


def part_reports():
    H1("8. Reports")
    P("Open <b>Reports</b> from the sidebar to see every report your role may open. Click a report's button to "
      "open it.")
    shot("landing-reports", "The Reports menu")
    H2("What every report can do")
    table([["Button", "What it does"],
           ["Date range fields", "Choose the period (on reports that support dates), then refresh."],
           ["Employee / Nozzle drop-downs", "Narrow the Attendant & Nozzle and Attendance reports."],
           ["Refresh", "Run the report again with the current filters."],
           ["Print", "Opens a print preview first, so you see it before paper is used; print from there."],
           ["Export PDF", "Saves a PDF (default folder: reports, next to the app data)."],
           ["Export Excel", "Saves an .xlsx spreadsheet."],
           ["Export CSV", "Saves a plain .csv file."]],
          [0.3, 0.7])
    H2("The reports")
    for slug, title, text in REPORTS:
        H3(title)
        P(text)
        shot(slug, f"{title} (sample demo data)")


def part_settings():
    H1("9. Settings - Backups and Audit Log")
    screen("page-backups", "Backups",
           "Protects you against a dead disk, a bad update or a mistake. A backup is a complete copy of the database.",
           "Roles with the Backup Manage permission (Admin, Owner, Manager by default).",
           [("Back Up Now", "Take a backup immediately."),
            ("Copy to USB / Network...", "Copy a backup to a USB stick or network folder. Do this regularly - a "
             "backup on the same drive as the database does not survive a disk failure."),
            ("Check Integrity", "Runs a full consistency check of the live database. Safe at any time; changes "
             "nothing."),
            ("Restore Selected", "Replace the live database with a chosen backup (reason required).")],
           notes=["Backups are taken automatically before any database update and once a day. Every backup is "
                  "verified right after it is made. A failed automatic backup never stops the app starting."],
           rules=["Restoring first takes a safety backup of the current database, so even a wrong restore can be "
                  "undone. Restart the app after a restore."])
    screen("page-audit-log", "Audit Log",
           "A read-only history of every recorded action: who did it, when, and what changed. It cannot be edited.",
           "Roles with the Audit View permission (Admin, Owner).",
           [("Filter", "Narrow by event type, user and date range."),
            ("Verify Trail", "Checks that the audit trail has not been tampered with outside the app.")],
           notes=["Use it to answer 'who cancelled this sale?' or 'who changed that price?'"])


def part_alerts():
    H1("10. Alerts")
    P("The <b>Alerts</b> button in the top bar shows how many things need attention and turns amber or red when "
      "any do. Open it for the list. Each alert is one plain sentence saying <b>what</b> is wrong, <b>where</b> "
      "(real tank, customer, employee or shift name) and <b>what to do</b>. Click an alert to open the exact "
      "screen it concerns.")
    H2("What raises an alert")
    B("Low fuel in a tank, fuel or cash variances, payment mismatches",
      "Attendance not yet marked, items waiting for your approval",
      "Customers overdue, supplier invoices past their due date",
      "No recent backup, or a database or audit-trail problem")
    H2("How alerts behave")
    B("You only see alerts for areas your role can access. Approvals only reach people who can give them.",
      "<b>There is no dismiss button - deliberately.</b> An alert is recalculated from live data each time, and "
      "disappears by itself when the problem is fixed (refill the tank, approve the expense, record the payment).",
      "So an empty list genuinely means nothing is outstanding. If the app could not work the list out, it says so "
      "instead of showing an empty list.",
      "The count refreshes about once a minute; opening the screen refreshes immediately.")
    WARN("Administrators: take special note of <b>Backup failure</b> (no backup in 48 hours), <b>Database error</b>, "
         "<b>The audit trail has been altered</b>, and a burst of <b>Refused actions</b> from one account. Treat the "
         "first three as urgent.")


def part_backup_recovery():
    H1("11. Backup and recovery")
    H2("A simple backup habit")
    N("At the start and end of each day, open <b>Settings -> Backups</b> and click <b>Back Up Now</b>.",
      "Click <b>Copy to USB / Network...</b> and copy it onto a USB stick kept somewhere safe (ideally away from "
      "the pump).",
      "Keep the start-of-day backup until you are sure the day's data is sound.")
    H2("Restoring a backup")
    N("Open <b>Backups</b> and select the backup you want.", "Click <b>Restore Selected</b>.",
      "Type the <b>reason</b> (it is audited).", "Confirm. The app saves a safety copy of the current database "
      "first.", "Close and reopen the app.")
    WARN("A restore rolls back <b>everything</b> since that backup, not just one wrong entry. For an everyday "
         "mistake use the correction action in that module (cancel, reverse, adjust) instead.")
    H2("If the app will not start")
    N("Open <b>%LOCALAPPDATA%\\PetrolPumpERP\\petrol_pump_erp.log</b> in Notepad and read the last lines.",
      "If it points at a damaged database, <b>do not delete it</b>. Rename it to petrol_pump.db.broken.",
      "Copy the newest file from the <b>backups</b> folder to <b>petrol_pump.db</b> and start the app again.",
      "If nothing in backups works, keep the broken file and the log for investigation.")
    H2("Power cut mid-sale")
    P("Restart the app and check the last sale on the Sales screen. The database is built to survive this - a "
      "transaction either completed or did not, never half. If unsure whether something saved, <b>look at the list "
      "screen rather than entering it again</b>.")


def part_daily():
    H1("12. Daily routine checklist")
    H2("Before the shift")
    B("Check the Alerts - especially low fuel and the backup alert.",
      "Confirm today's fuel prices are right (Masters -> Fuel Prices).",
      "Mark the previous day's attendance if it was missed.")
    H2("Opening the shift (supervisor)")
    N("Operations -> Shifts -> <b>+ Open Shift</b>.",
      "<b>Assign Nozzle</b> for each attendant with the opening meter reading from the dispenser face.")
    H2("During the shift")
    B("Attendants record every sale in <b>Terminal</b>. Use the UPI reference / card code fields.",
      "Credit sales: choose the customer; the app checks their limit.",
      "Mistake? <b>Sales -> Cancel Selected</b> with a reason. Never re-enter.",
      "Deliveries: follow the Procurement steps.")
    H2("Closing the shift")
    N("Enter each <b>closing meter reading</b> and complete the assignments.", "<b>Close Shift</b>.",
      "<b>Reconciliation -> + Reconcile Shift</b>: count the cash and enter UPI and card totals.",
      "Manager approves any flagged variance.",
      "Reports -> <b>Daily Summary</b>: compare with your own count.",
      "Settings -> Backups -> <b>Back Up Now</b>, then <b>Copy to USB / Network...</b>.")
    H2("Weekly / monthly")
    B("Approve pending expenses and leave requests.", "Record customer payments; review Customer Outstanding.",
      "Record supplier invoices and payments.", "Review Fuel Movement for unusual adjustments.",
      "Skim the Audit Log for refused actions.")


def part_security():
    H1("13. Security and data protection")
    H2("What the app protects")
    B("Passwords are never stored - only salted, iterated hashes.",
      "Sign-in sessions are stored hashed, so a stolen database yields no usable sessions.",
      "The audit trail is append-only and hash-chained, so tampering is detectable.",
      "Every important action needs a permission, and many need a written reason.",
      "The app never uses the internet and sends nothing anywhere.")
    H2("What YOU must do")
    P("The database file is not encrypted. Anyone who can copy the file can read every sale, salary and balance. "
      "The correct protection for a desktop application is the operating system's disk encryption:")
    N("<b>Turn on BitLocker</b> on the drive holding the app and its data (Windows: Settings -> Privacy & security "
      "-> Device encryption). Keep the recovery key off the PC.",
      "<b>Encrypt your backup USB sticks</b> (BitLocker To Go). An unencrypted backup on a lost stick is as bad as a "
      "stolen PC.",
      "Use <b>separate Windows accounts</b> for staff who should not reach the data folder.",
      "<b>Never email or cloud-sync the database file.</b>",
      "Give every person their own login. Use <b>Lock</b> when leaving the counter.")


def part_trouble():
    H1("14. Troubleshooting and questions")
    table([["What you see", "What is happening and what to do"],
           ["Every sale is refused", "Fuel prices are still 0.00. Set them in Masters -> Fuel Prices."],
           ["A credit sale is refused", "The customer has no credit account, or the sale would exceed the limit."],
           ["Attendant sees almost nothing", "Correct - attendants only see their own shift and the sales terminal."],
           ["I cannot sell - 'not assigned'", "You must be assigned to a nozzle in an open shift (Shifts -> Assign "
            "Nozzle)."],
           ["Shift will not close", "A nozzle assignment is still active. Complete it with a closing meter reading."],
           ["Nozzle cannot be deactivated", "It is assigned in an open shift."],
           ["Account locked", "5 wrong passwords. Wait 15 minutes or ask an administrator to unlock it."],
           ["Forgot my password", "Use the login screen's forgot-password link with a code from an administrator, or "
            "ask the administrator to reset it."],
           ["A screen or button is missing", "Your role does not have that permission. Ask your administrator."],
           ["Alerts shows no number at first", "The count refreshes about once a minute; opening the screen "
            "recalculates it."],
           ["A total looks wrong", "Do not re-enter anything. Tell your manager. Find the original record and use "
            "its correction action, or check the Audit Log."],
           ["Windows warns about the installer", "Click More info -> Run anyway (the program is not signed with a "
            "paid certificate)."],
           ["App will not start", "See chapter 11 - read the log, then restore from a backup."]],
          [0.32, 0.68])
    H2("Getting more help")
    P("The <b>Support</b> link at the bottom of the sidebar shows version and support information. When you ask "
      "for help, say which screen you were on, what you clicked, and the exact message shown. The log file at "
      "%LOCALAPPDATA%\\PetrolPumpERP\\petrol_pump_erp.log helps whoever supports you.")


def part_appendix():
    H1("Appendix A - Optional settings (config.env)")
    P("Most behaviour works out of the box. To change a setting, create or edit <b>config.env</b> in "
      "%LOCALAPPDATA%\\PetrolPumpERP\\ with lines like <b>SESSION_TIMEOUT_HOURS=12</b>. Changes apply the next time "
      "the app starts.")
    table([["Setting", "Default", "What it controls"],
           ["SESSION_TIMEOUT_HOURS", "8", "How long an idle session stays signed in"],
           ["AUTO_BACKUP_INTERVAL_HOURS", "24", "How old the newest backup may be before the app takes another on startup"],
           ["LOG_LEVEL", "INFO", "Log detail: DEBUG, INFO, WARNING or ERROR"]],
          [0.38, 0.12, 0.5])
    H1("Appendix B - Glossary")
    table([["Term", "Meaning"],
           ["Audit log", "Permanent record of who did what and when."],
           ["Backup", "A complete copy of the database."],
           ["Dip reading", "Measuring the fuel level in a tank with a dipstick."],
           ["GSTIN", "The business's GST registration number, printed on receipts."],
           ["Meter reading", "The totaliser number on a nozzle; closing minus opening = litres dispensed."],
           ["Opening / closing stock", "Fuel in a tank at the start / end of a period."],
           ["Reconciliation", "Comparing expected with counted cash, UPI, card or fuel."],
           ["Tender", "A way of paying: cash, UPI, card, credit."],
           ["UPI", "India's instant bank-payment system, used at the counter with a QR code or app."],
           ["Variance", "The difference between expected and counted. Not an accusation."],
           ["Void / reverse / adjust", "Correcting a record by adding a visible correcting entry, never deleting."]],
          [0.28, 0.72])


def main():
    cover()
    part_intro()
    part_install()
    part_navigation()
    part_roles()
    part_setup()
    part_masters()
    part_operations()
    part_reports()
    part_settings()
    part_alerts()
    part_backup_recovery()
    part_daily()
    part_security()
    part_trouble()
    part_appendix()
    Manual(OUT).multiBuild(story)
    print("wrote", OUT, f"{OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
