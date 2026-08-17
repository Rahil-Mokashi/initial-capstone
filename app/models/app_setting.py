import uuid

from sqlalchemy import Column, String, Text

from .base import Base, EntityMixin


class AppSetting(EntityMixin, Base):
    """Company profile and installation-wide preferences.

    A SINGLE-ROW table, not a key/value store. Both shapes are defensible
    and the choice is worth stating: a key/value table is flexible but
    every read needs a lookup and a cast, and nothing stops two callers
    disagreeing about whether "gst_number" or "gstin" is the key. A
    single row with real typed columns gets the schema to enforce what
    exists, which matches how the rest of this app is built - the same
    reasoning that put value invariants in CHECK constraints rather than
    only in Python.

    The company profile fields exist because printed receipts and reports
    currently carry no business identity at all, which makes them
    unusable as customer-facing documents - a receipt with no pump name,
    address or GST number is not a receipt, it is a slip of paper.
    """

    __tablename__ = "app_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # --- Company profile: what appears on printed documents -------------
    company_name = Column(String(200), nullable=True)
    address_line1 = Column(String(200), nullable=True)
    address_line2 = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    phone = Column(String(40), nullable=True)
    email = Column(String(120), nullable=True)
    gst_number = Column(String(32), nullable=True)
    licence_number = Column(String(64), nullable=True)
    receipt_footer = Column(Text, nullable=True)

    # --- Operational preferences ---------------------------------------
    # Where "Copy to USB / Network..." defaults to, so an operator does not
    # have to re-find the drive every time - the friction that stops
    # off-device backups actually happening.
    offsite_backup_dir = Column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<AppSetting(company_name={self.company_name!r})>"

    @property
    def has_company_profile(self) -> bool:
        """Whether there is enough here to head a printed document."""
        return bool(self.company_name and self.company_name.strip())

    def address_lines(self) -> list[str]:
        """The address as printable lines, skipping the empty ones."""
        city_line = ", ".join(p for p in (self.city, self.state) if p)
        if city_line and self.postal_code:
            city_line = f"{city_line} - {self.postal_code}"
        elif self.postal_code:
            city_line = self.postal_code
        return [line for line in (self.address_line1, self.address_line2, city_line) if line]
