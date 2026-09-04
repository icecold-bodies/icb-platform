from sqlalchemy import create_engine, text as _sa_text, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, Index, UniqueConstraint, event
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Use LONGTEXT on MySQL for JSON payloads that can exceed TEXT's 64 KB cap
# (e.g. a saved costing result_json with the full BOM + soft-excluded optional
# items easily clears 100 KB on busy trailers). SQLite has no length limit on
# Text, so the variant is a no-op there.
_BigJson = Text().with_variant(LONGTEXT(), "mysql")
from datetime import datetime, timezone
import os
from .config import settings

# ── Database engine (PostgreSQL only) ───────────────────────────────────────
# The unified monorepo (WO v4.12) is PostgreSQL-only via psycopg. The legacy
# SQLite (local dev) and MySQL (prod) engine branches were removed; schema/DDL
# is owned by Alembic (backend/alembic/), so nothing here touches the DB or
# creates tables at import time.
DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=15,
    pool_timeout=10,
    # Refresh pooled connections every 10 min so a long-idle connection does not
    # come back dead and tax the next request with a reconnect.
    pool_recycle=600,
    # Cap the TCP handshake/auth phase rather than waiting the OS default (~75s)
    # when the database is genuinely unreachable.
    connect_args={"connect_timeout": 10},
)


@event.listens_for(engine, "connect")
def _set_search_path(dbapi_conn, conn_record):
    """WO v4.13: every connection resolves icb_mes first, then icb_costings, then
    public. MES models are explicitly schema-qualified; this keeps any unqualified
    names and the v_calculation_records_legacy view resolving predictably."""
    cur = dbapi_conn.cursor()
    try:
        cur.execute("SET search_path TO icb_mes, icb_costings, public")
    finally:
        cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def switch_db(new_url: str):
    """Hot-swap the database connection at runtime (admin only)."""
    global engine, SessionLocal, DATABASE_URL
    DATABASE_URL = new_url
    engine = create_engine(new_url, pool_pre_ping=True, pool_size=5,
                           max_overflow=10, pool_recycle=600)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Invalidate the process-wide TTL caches — they hold rows loaded via the
    # OLD engine's SessionLocal (sections, formulas, global vars). Without this
    # the first /api/calculate after a db_choice swap returns stale section
    # flags (e.g. OPTIONAL EXTRAS' is_optional reads False because the prior
    # engine's snapshot had it unflagged), even though the new engine's DB has
    # the right value. Bug surfaced in WO v4.7.1.
    try:
        from . import cache as _cache
        _cache.invalidate_all()
    except Exception:
        pass


def get_db_info():
    """Return (db_env_label, db_detail, db_is_prod) for the active connection.
    PostgreSQL-only: a localhost connection is treated as DEV, anything else as
    PROD (drives the UI footer banner)."""
    url = DATABASE_URL
    host = ""
    try:
        after_at = url.split("@", 1)[1]
        host = after_at.split("/")[0].split(":")[0]
        dbname = after_at.split("/", 1)[1].split("?")[0]
        detail = f"{host} / {dbname}"
    except Exception:
        detail = "PostgreSQL"
    if host in ("localhost", "127.0.0.1", "::1", ""):
        return "DEV (PostgreSQL)", detail, False
    return "PROD (PostgreSQL)", detail, True


class Branch(Base):
    """Operating branch (single-tenant Icecold, multi-branch foundation).
    WO v4.12 (Phase 1) creates this table + nullable branch_id FKs on the
    operational tables, backfilled to JHB. No branch UI yet (Phase 2)."""
    __tablename__ = "branches"
    id         = Column(Integer, primary_key=True)
    code       = Column(String(8), unique=True, nullable=False)   # JHB | CPT | CEN
    name       = Column(String(100), nullable=False)
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user")
    # v1.39.3 backport (migration 0030) — real address for Pre-Job Card check auto-send
    # (Sales/Planner signers + CC). server_default '' so pre-0030 rows are valid; the
    # seed_phase1_users script sets the three Phase-1 addresses.
    email = Column(String(255), nullable=False, server_default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime, nullable=True)  # stamped on successful login
    calculations = relationship("CalculationRecord", back_populates="user", foreign_keys="CalculationRecord.user_id")
    approved_calculations = relationship("CalculationRecord", back_populates="approver", foreign_keys="CalculationRecord.approved_by_user_id")

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def can_view_full_cost(self):
        return self.role in ("admin", "full")


# ─── Fine-grained permissions ───────────────────────────────────────────────

class Permission(Base):
    """Catalogue of named capabilities. Strings are the single source of truth
    (e.g. 'bom.view_prices', 'export.excel'). Seeded by _bootstrap_permissions."""
    __tablename__ = "permissions"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(64), unique=True, nullable=False)
    description = Column(String(255))
    category    = Column(String(32), default="general")  # for grouping in admin UI


class RolePermission(Base):
    """Default permission grant for a role (admin/full/user). The admin role
    is treated as wildcard in code — RolePermission rows for 'admin' are
    informational only."""
    __tablename__ = "role_permissions"
    id            = Column(Integer, primary_key=True)
    role          = Column(String(20), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False)
    __table_args__ = (UniqueConstraint("role", "permission_id", name="uq_role_perm"),)


class UserPermission(Base):
    """Per-user override on top of role defaults. effect='allow' grants a perm
    the role doesn't have; effect='deny' revokes a perm the role does have."""
    __tablename__ = "user_permissions"
    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    permission_id = Column(Integer, ForeignKey("permissions.id"), nullable=False)
    effect        = Column(String(10), default="allow")  # 'allow' | 'deny'
    __table_args__ = (UniqueConstraint("user_id", "permission_id", name="uq_user_perm"),)


class MaterialCategory(Base):
    __tablename__ = "material_categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    description = Column(String(500))
    materials = relationship("Material", back_populates="category")


class Material(Base):
    __tablename__ = "materials"
    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False)
    category_id = Column(Integer, ForeignKey("material_categories.id"))
    unit_of_measure = Column(String(50), default="each")
    price_per_unit = Column(Float, default=0.0)
    supplier = Column(String(200))
    material_code = Column(String(100))
    sap_code = Column(String(100))
    size = Column(String(200))
    manufacture_sub_category = Column(String(100))  # Source sheet in PRICE 2017 MARCH.xlsx
    last_bulk_update_at   = Column(DateTime, nullable=True)
    last_bulk_update_note = Column(String(500), nullable=True)
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    category = relationship("MaterialCategory", back_populates="materials")
    bom_items = relationship("BillOfMaterial", back_populates="material", foreign_keys="BillOfMaterial.material_id")
    price_history = relationship("PriceHistory", back_populates="material")


class TrailerType(Base):
    __tablename__ = "trailer_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False)
    description = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    default_length     = Column(Float, nullable=True)
    default_width      = Column(Float, nullable=True)
    default_height     = Column(Float, nullable=True)
    markup_percentage  = Column(Float, default=0.0)
    # When True, this body type's BOM overrides are excluded from bulk material
    # price propagation — they are managed independently.
    protect_overrides  = Column(Boolean, default=False)
    # Phase 3 calculator opt-in. When True, the calculator honours the new
    # configurator fields (bom_sections.archived_at + body_option_master_id,
    # bill_of_materials.bom_conditions) in addition to the legacy gating.
    # Toggleable per trailer from /admin/templates so rollout can be gradual.
    configurator_v2 = Column(Boolean, default=False, nullable=False)
    # Quote/report assignment. group_id binds to a TrailerGroup which carries
    # the default ReportTemplate. override_report_template_id wins per-trailer
    # so one trailer in a group can use a different template.
    group_id                  = Column(Integer, ForeignKey("trailer_groups.id"), nullable=True)
    override_report_template_id = Column(Integer, ForeignKey("report_templates.id"), nullable=True)
    bom_items    = relationship("BillOfMaterial", back_populates="trailer_type")
    calculations = relationship("CalculationRecord", back_populates="trailer_type")
    ratios       = relationship("TrailerRatio", back_populates="trailer_type", order_by="TrailerRatio.sort_order")
    group              = relationship("TrailerGroup", back_populates="trailer_types", foreign_keys=[group_id])
    override_template  = relationship("ReportTemplate", foreign_keys=[override_report_template_id])


class Formula(Base):
    __tablename__ = "formulas"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    description = Column(String(500))
    expression = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class GlobalVariable(Base):
    __tablename__ = "global_variables"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    value = Column(Float, nullable=False, default=0.0)
    description = Column(String(500))


class BillOfMaterial(Base):
    __tablename__ = "bill_of_materials"
    id = Column(Integer, primary_key=True)
    trailer_type_id = Column(Integer, ForeignKey("trailer_types.id"))
    material_id = Column(Integer, ForeignKey("materials.id"))
    formula_expression = Column(Text, default="1")
    waste_percentage = Column(Float, default=0.0)
    notes = Column(String(500))
    sort_order = Column(Integer, default=0)
    # bom_section: legacy string — kept for display/sort/fallback.
    # bom_section_id: FK to bom_sections.id — authoritative for multiplier lookup.
    bom_section = Column(String(100))
    bom_section_id = Column(Integer, ForeignKey("bom_sections.id"), nullable=True)
    # Import-traceability and richer formula metadata (added by v2 importer).
    excel_formula       = Column(Text)          # original Excel formula text (col H)
    unit_price_snapshot = Column(Float)         # cached unit price at import time (col G)
    source_cell         = Column(String(64))    # e.g. "H27" or "FORMULA SKINS!D49" for audit
    is_formula_skin     = Column(Boolean, default=False)
    highlight_color     = Column(String(20))    # e.g. "red" for formula-skin children
    # Per-BOM-row permanent price override. When set, takes precedence over
    # material.price_per_unit so the same material can have different prices
    # in different sections (e.g. EPS in FRONT vs EPS in SIDES).
    unit_price_override = Column(Float)
    # v1.52: stamped by bulk price imports on every line they touch (price,
    # description or override reset). Line-level because PU prices live in the
    # override and SPLIT repoints can land on pre-existing materials — material
    # stamps can't mark those. Read-side 30-day expiry; never cleared.
    price_updated_at = Column(DateTime(timezone=True), nullable=True)
    # Body-options fields — populated by the BODY OPTIONS section of the Excel import.
    # is_body_option: row is a selectable option (not a fixed BOM line).
    # body_option_group: mutual-exclusion group (FRONT, DRD, SRD, SIDES, ROOF, FLOOR …).
    # body_option_default: True when the Excel Y/N column = Y at import time.
    # _id columns are FK; string columns kept for display/sort/fallback.
    is_body_option       = Column(Boolean, default=False)
    body_option_group    = Column(String(100))
    body_option_group_id = Column(Integer, ForeignKey("body_option_groups.id"), nullable=True)
    body_option_subgroup    = Column(String(100))
    body_option_subgroup_id = Column(Integer, ForeignKey("body_option_subgroups.id"), nullable=True)
    body_option_default  = Column(Boolean, default=False)
    # Calculator 2 default: when True this row's exclude tick starts ON in
    # Calculator 2 (line left out of the costing). Admin-set via the Body
    # Templates edit modal; re-applied on every Calculator 2 load.
    calc2_default_excluded = Column(Boolean, default=False)
    # Per-item inclusion mode — replaces juggling is_body_option +
    # body_option_subgroup by hand. Values:
    #   'always' — included whenever the row's section is included (the
    #              default for every existing row before this column existed)
    #   'single' — radio-button choice within selection_group
    #   'multi'  — independent checkbox toggle
    # Always written through to the legacy fields on save so the calculator
    # engine continues to work unchanged: 'single'/'multi' set
    # is_body_option=1; 'single' also writes selection_group →
    # body_option_subgroup so the existing radio constraint logic kicks in.
    selection_mode  = Column(String(16), default="always", nullable=False)
    selection_group = Column(String(100), nullable=True)
    # Body Configurator Phase 2: per-item AND conditions as JSON string.
    # Example: '[{"option":"BAKERY BODY","equals":"Y"},{"option":"DRY FREIGHT","equals":"Y"}]'.
    # NULL/empty means "no condition" — same as the legacy body_option_group_id gate.
    bom_conditions = Column(Text, nullable=True)
    # Body Variables: numeric value (metres) for is_body_option rows,
    # referenceable from BOM formulas as {NAME} tokens (e.g. {FRONT EPS}).
    variable_value       = Column(Float, nullable=True)
    # For regular section items whose inclusion depends on a body option choice.
    # body_option_linked: legacy string name — kept for display/fallback only.
    # body_option_linked_id: FK to materials.id — authoritative; replaces string matching.
    body_option_linked = Column(String(200))
    body_option_linked_id = Column(Integer, ForeignKey("materials.id"), nullable=True)
    # Skin formula pricing — when set, unit price is computed from the formula
    # instead of material.price_per_unit. Region selects std vs KZN ingredient prices.
    skin_formula_id     = Column(Integer, ForeignKey("skin_formulas.id", ondelete="SET NULL"), nullable=True)
    skin_formula_region = Column(String(20), nullable=True, default="standard")  # 'standard' | 'kzn'
    taping_block_id     = Column(Integer, ForeignKey("taping_blocks.id", ondelete="SET NULL"), nullable=True)
    floor_plate_id      = Column(Integer, ForeignKey("floor_plates.id", ondelete="SET NULL"), nullable=True)
    mounting_cleat_id   = Column(Integer, ForeignKey("mounting_cleats.id", ondelete="SET NULL"), nullable=True)
    trailer_type = relationship("TrailerType", back_populates="bom_items")
    material = relationship("Material", back_populates="bom_items", foreign_keys="BillOfMaterial.material_id")
    linked_material = relationship("Material", foreign_keys="BillOfMaterial.body_option_linked_id")
    section = relationship("BOMSection", foreign_keys="BillOfMaterial.bom_section_id")
    opt_group    = relationship("BodyOptionGroup",    foreign_keys="BillOfMaterial.body_option_group_id")
    opt_subgroup = relationship("BodyOptionSubgroup", foreign_keys="BillOfMaterial.body_option_subgroup_id")
    skin_formula   = relationship("SkinFormula",   foreign_keys=[skin_formula_id],   back_populates="bom_items")
    taping_block   = relationship("TapingBlock",   foreign_keys=[taping_block_id],   back_populates="bom_items")
    floor_plate    = relationship("FloorPlate",    foreign_keys=[floor_plate_id],    back_populates="bom_items")
    mounting_cleat = relationship("MountingCleat", foreign_keys=[mounting_cleat_id], back_populates="bom_items")


class Customer(Base):
    __tablename__ = "customers"
    id            = Column(Integer, primary_key=True)
    branch_id     = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)  # WO v4.12 multi-branch
    bp_code       = Column(String(50))
    name          = Column(String(300), nullable=False)
    email         = Column(String(300))
    telephone     = Column(String(100))
    # v1.47 Lane D (migration 0041) — the customer's VAT number, printed in the
    # quotation-document header ("Vat Num - Partner"). Free text: ICB quotes
    # cross-border customers, so it must hold whatever their jurisdiction issues.
    vat_number    = Column(String(50), nullable=True)
    is_active     = Column(Boolean, default=True)
    # WO v4.34.1 §0.2 — single-table dealer flag: an entity can be BOTH a biller and a chassis
    # supplier (Burt). Pure dealers are customers rows with is_dealer=true + nullable billing fields.
    is_dealer     = Column(Boolean, nullable=False, default=False, server_default=_sa_text("false"))
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    calculations  = relationship("CalculationRecord", back_populates="customer")
    contacts      = relationship("CustomerContact", back_populates="customer",
                                 cascade="all, delete-orphan")
    end_users     = relationship("CustomerEndUser", back_populates="customer",
                                 cascade="all, delete-orphan")


class CustomerContact(Base):
    """WO v4.34.1 §0.6 — multiple contacts per customer (Nadie's reality). The customer row's
    email/telephone stay as a denormalised cache (deprecate-not-drop, ADR 0016); the primary
    contact is the going-forward source of truth. Partial unique index = one is_primary per
    customer; soft-delete via is_active."""
    __tablename__ = "customer_contacts"
    __table_args__ = (
        Index("ix_customer_contacts_customer", "customer_id"),
        Index("uq_customer_contacts_one_primary", "customer_id", unique=True,
              postgresql_where=_sa_text("is_primary")),
    )
    id          = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    name        = Column(String(200))                  # the contact person (nullable; migrated rows have none)
    role        = Column(String(100))                  # free text in v4.34.1 (§0.12; enum is v4.35+)
    email       = Column(String(300))
    telephone   = Column(String(100))
    is_primary  = Column(Boolean, nullable=False, default=False, server_default=_sa_text("false"))
    is_active   = Column(Boolean, nullable=False, default=True, server_default=_sa_text("true"))
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))
    created_by  = Column(String(128))
    updated_by  = Column(String(128))
    customer    = relationship("Customer", back_populates="contacts")


class CustomerEndUser(Base):
    """WO v1.47 lane B (Nadie, 17 Aug) — the END USER: ICB's customer is often a reseller or a
    middleman, and the body is actually FOR someone else. One row = one end-user COMPANY plus
    its contact PERSON (Nadie's "table that contains the end user and the contact person").
    Exact twin of CustomerContact, one level out: partial unique index = one is_primary per
    customer; soft-delete via active. company_name is the only required field."""
    __tablename__ = "customer_end_users"
    __table_args__ = (
        Index("ix_customer_end_users_customer", "customer_id"),
        Index("uq_customer_end_users_one_primary", "customer_id", unique=True,
              postgresql_where=_sa_text("is_primary")),
    )
    id                = Column(Integer, primary_key=True)
    customer_id       = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"),
                               nullable=False)
    company_name      = Column(String(200), nullable=False)   # the end-user company
    contact_name      = Column(String(200))                   # their person (all optional)
    contact_email     = Column(String(300))
    contact_telephone = Column(String(100))
    contact_role      = Column(String(100))
    notes             = Column(Text)
    is_primary        = Column(Boolean, nullable=False, default=False,
                               server_default=_sa_text("false"))
    active            = Column(Boolean, nullable=False, default=True,
                               server_default=_sa_text("true"))
    created_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                               onupdate=lambda: datetime.now(timezone.utc))
    created_by        = Column(String(128))
    updated_by        = Column(String(128))
    customer          = relationship("Customer", back_populates="end_users")


class TrailerRatio(Base):
    __tablename__ = "trailer_ratios"
    id              = Column(Integer, primary_key=True)
    trailer_type_id = Column(Integer, ForeignKey("trailer_types.id"))
    ratio_value     = Column(Float, nullable=False)
    label           = Column(String(100))
    sort_order      = Column(Integer, default=0)
    trailer_type    = relationship("TrailerType", back_populates="ratios")


class PriceHistory(Base):
    __tablename__ = "price_history"
    id = Column(Integer, primary_key=True)
    material_id = Column(Integer, ForeignKey("materials.id"))
    old_price = Column(Float)
    new_price = Column(Float)
    changed_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    changed_by = Column(String(100))
    material = relationship("Material", back_populates="price_history")


class BomOverrideHistory(Base):
    """Audit trail for bulk changes to bill_of_materials.unit_price_override.
    Rows share a batch_at timestamp so the whole batch can be undone atomically."""
    __tablename__ = "bom_override_history"
    id               = Column(Integer, primary_key=True)
    bom_id           = Column(Integer, ForeignKey("bill_of_materials.id"))
    material_id      = Column(Integer)
    trailer_type_id  = Column(Integer)
    trailer_type_name = Column(String(300))
    material_name    = Column(String(300))
    old_price        = Column(Float)
    new_price        = Column(Float)
    changed_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    batch_at         = Column(DateTime)  # grouping key — all rows in one "Apply" share this


class CalculationRecord(Base):
    __tablename__ = "calculations"
    id = Column(Integer, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)  # WO v4.12 multi-branch
    trailer_type_id = Column(Integer, ForeignKey("trailer_types.id"))
    user_id         = Column(Integer, ForeignKey("users.id"))
    customer_id     = Column(Integer, ForeignKey("customers.id"), nullable=True)
    dimensions_json = Column(Text)
    result_json     = Column(_BigJson)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    approved_at     = Column(DateTime, nullable=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status          = Column(String(24), nullable=False, default="pending")
    # Status values: pending | accepted | declined | pre_job_sent | pre_job_confirmed
    # The two MES-only states (pre_job_sent, pre_job_confirmed) are written by the
    # /api/calculations/{id}/pre-job-card and /pre-job-confirm endpoints used by
    # the Icecold Bodies MES React mockup (Addendum v1.2.1).
    decline_reason  = Column(Text, nullable=True)
    quote_number    = Column(String(64), nullable=True, index=True)  # Immutable once assigned. Formatted via QuoteCounter template.
    is_repair       = Column(Boolean, default=False)  # quote is for repair work, not a new build
    # v1.49 (0043) — SOFT delete. NULL deleted_at = live; a value hides the costing
    # from the board until the "Deleted" pill is selected. deleted_by is the
    # actor's USERNAME snapshotted at write time (house audit idiom), so the
    # record survives that user being renamed or removed.
    deleted_at      = Column(DateTime(timezone=True), nullable=True, index=True)
    deleted_by      = Column(String(120), nullable=True)
    # Cost Calculator discount (WO v4.30 port from GRP-Costing-System d2da5bf). Applied to the selling
    # price; net_total is the post-discount headline (also mirrored into result_json). NULLs = no
    # discount, behaviour identical to before. Columns exist on the shared prod DB (faje's d2da5bf
    # deploy); migration 0015 adds them (guarded/idempotent) to icb's Alembic-owned CI/local DBs — a
    # no-op on prod where they already exist (§0.2a / WO §2: shared schema unchanged at cutover).
    discount_kind   = Column(String(16), nullable=True)   # 'percent' | 'amount' | NULL
    discount_input  = Column(Float, nullable=True)        # raw value typed (the % or the flat amount)
    discount_amount = Column(Float, nullable=True)        # computed currency discount
    net_total       = Column(Float, nullable=True)        # selling_price - discount_amount (headline)
    # WO v4.33 §0.13 (migration 0017): the sales rep this quote is being done FOR, captured at
    # quote time when Nadie knows it (nullable — may be unknown). Defaults the Pre-Job Card's
    # Sales Rep dropdown; user_id above (the creator) is the soft fallback when this is NULL.
    sales_rep_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    # MES Pre-Job Card flow (Step 3 of the Icecold Bodies process).
    pre_job_sent_at      = Column(DateTime, nullable=True)
    pre_job_confirmed_at = Column(DateTime, nullable=True)
    job_number_assigned  = Column(String(32), nullable=True)  # Set at pre_job_confirmed time.
    # Repair quotes: planner-selected phase entry points (Vacuum / Doors / GRP, etc.).
    # JSON shape: [{"phase": "VACUUM", "bay_id": "VAC-2", "estimated_hours": 6}, ...]
    repair_phases_json   = Column(Text, nullable=True)
    # MES Pre-Job Card sign-off gate (Work Order v4). Two role-gated signoffs;
    # when BOTH are non-null the signoff endpoint auto-progresses status through
    # 'pre_job_confirmed' (transient) to 'planning' in one transaction.
    pre_job_signoff_sales_at              = Column(DateTime, nullable=True)
    pre_job_signoff_sales_by              = Column(String(64), nullable=True)
    pre_job_signoff_sales_attestation     = Column(Text, nullable=True)
    pre_job_signoff_production_at         = Column(DateTime, nullable=True)
    pre_job_signoff_production_by         = Column(String(64), nullable=True)
    pre_job_signoff_production_attestation = Column(Text, nullable=True)
    # Planning hand-off (Work Order v4). Set when the Planning role acknowledges
    # the new job on the Planning Board (stops the pulsing card + dashboard pill).
    planning_acknowledged_at = Column(DateTime, nullable=True)
    planning_acknowledged_by = Column(String(64), nullable=True)
    # Chassis ETA capture (Work Order v4.2). Required by the Planning role
    # BEFORE planning_acknowledged_at can be set — gates the Acknowledge button
    # on the Planning Ack panel. chassis_data_json carries vin, model, dealer,
    # tail_lift_code, and the in-house BOM as a single JSON blob (matches the
    # existing repair_phases_json pattern; future fields don't need new ALTERs).
    chassis_eta              = Column(DateTime, nullable=True)
    chassis_eta_captured_at  = Column(DateTime, nullable=True)
    chassis_eta_captured_by  = Column(String(64), nullable=True)
    chassis_data_json        = Column(Text, nullable=True)
    # Chassis arrival confirmation (Work Order v4.3). The planner ticks the
    # "Chassis received" box on the job card once the chassis physically
    # arrives at Icecold. Records the receipt date + who confirmed.
    chassis_received_at      = Column(DateTime, nullable=True)
    chassis_received_by      = Column(String(64), nullable=True)
    # Customer-contact snapshot (migration 0035). The contact person this quote is FOR
    # ATTENTION OF, captured as a write-time snapshot (ADR 0016 deprecate-not-drop /
    # chassis_records edited_by_name pattern): later contact edits or deletes must not
    # rewrite quote history. contact_id survives soft-delete (is_active=false) and goes
    # NULL only on a hard DELETE of the contact row (ondelete=SET NULL) — the snapshot
    # columns keep the display values either way.
    contact_id        = Column(Integer, ForeignKey("customer_contacts.id", ondelete="SET NULL"),
                               nullable=True)
    contact_name      = Column(String(200), nullable=True)
    contact_email     = Column(String(300), nullable=True)
    contact_telephone = Column(String(100), nullable=True)
    contact_role      = Column(String(100), nullable=True)
    # End-user snapshot (migration 0040, WO v1.47 lane B). The END USER this body is
    # actually FOR when the customer is a reseller/middleman — same write-time snapshot
    # discipline as the contact block above, written by the same approve-path chokepoint
    # and never rewritten by later edits to the end-user book. Fully optional: a costing
    # with no end user leaves every column NULL and behaves exactly as before.
    end_user_id                 = Column(Integer,
                                         ForeignKey("customer_end_users.id", ondelete="SET NULL"),
                                         nullable=True)
    end_user_company            = Column(String(200), nullable=True)
    end_user_contact_name       = Column(String(200), nullable=True)
    end_user_contact_email      = Column(String(300), nullable=True)
    end_user_contact_telephone  = Column(String(100), nullable=True)
    end_user_contact_role       = Column(String(100), nullable=True)
    trailer_type = relationship("TrailerType", back_populates="calculations")
    user         = relationship("User", back_populates="calculations", foreign_keys=[user_id])
    approver     = relationship("User", back_populates="approved_calculations", foreign_keys=[approved_by_user_id])
    customer     = relationship("Customer", back_populates="calculations")


class ChassisConstant(Base):
    """Fixed parts every chassis includes (STEEL + RUNNING GEAR blocks).
    qty_per_metre lets length-driven items scale; qty_constant is added on top.
    Final qty = qty_per_metre * length + qty_constant."""
    __tablename__ = "chassis_constants"
    id              = Column(Integer, primary_key=True)
    category        = Column(String(20), nullable=False)   # 'steel' | 'running_gear'
    name            = Column(String(200), nullable=False)
    qty_per_metre   = Column(Float, default=0.0)
    qty_constant    = Column(Float, default=0.0)
    unit_price      = Column(Float, default=0.0)
    sort_order      = Column(Integer, default=0)
    is_active       = Column(Boolean, default=True)


class ChassisOption(Base):
    """Selectable chassis parts the user picks from dropdowns:
    suspension (axle systems), brake kits, tyres, rims, lifting axles."""
    __tablename__ = "chassis_options"
    id              = Column(Integer, primary_key=True)
    kind            = Column(String(20), nullable=False)   # 'suspension' | 'brake' | 'tyre' | 'rim' | 'lifting_axle'
    label           = Column(String(200), nullable=False)
    axle_count      = Column(Integer, nullable=True)        # 1/2/3 for suspension+brake; null otherwise
    tyre_style      = Column(String(20), nullable=True)     # 'dual' | 'super_single' for tyre+rim; null otherwise
    price           = Column(Float, default=0.0)
    sort_order      = Column(Integer, default=0)
    is_active       = Column(Boolean, default=True)


class QuoteCounter(Base):
    """One row PER NUMBERING SERIES, holding that series' next integer and the
    format template the admin has chosen. Numbers, once assigned to a
    calculation, are immutable — changing the template here only affects future
    records.

    v1.47 Lane D (migration 0042): this used to be a singleton ("id=1 always").
    The repair QUOTATION DOCUMENT carries its own R-prefixed number that must
    never perturb the body-costing sequence, so the table is now keyed by
    `series` (unique index). 'quote' IS the original body-costing line and is
    unchanged; 'repair_doc' is the R-series.
    """
    __tablename__ = "quote_counter"
    id              = Column(Integer, primary_key=True)
    series          = Column(String(32), nullable=False, default="quote",
                             server_default=_sa_text("'quote'"))
    next_value      = Column(Integer, nullable=False, default=1)
    format_template = Column(String(255), nullable=False, default="{user_initial}{counter}/{month}/{year}")
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))


class PDFTemplate(Base):
    __tablename__ = "pdf_templates"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    trailer_type_id = Column(Integer, ForeignKey("trailer_types.id"))
    template_data = Column(Text, nullable=False)  # JSON string containing template configuration
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    trailer_type = relationship("TrailerType")


class Theme(Base):
    __tablename__ = "themes"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500), nullable=True)
    css_path = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CommodityQuote(Base):
    """Daily close prices for commodity / equity proxy tickers used to surface
    price-trend hints next to material sub-categories on /admin/materials."""
    __tablename__ = "commodity_quotes"
    id     = Column(Integer, primary_key=True)
    ticker = Column(String(50), nullable=False, index=True)
    date   = Column(DateTime, nullable=False, index=True)
    close  = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")


class AdminSetting(Base):
    """Generic key/value store for admin-controlled app settings."""
    __tablename__ = "admin_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ReportTemplate(Base):
    """A renderable report template. Two backends:
    - kind='html'        → uses app/templates/reports/<slug>.html via WeasyPrint
    - kind='pdf_overlay' → renders by drawing fields onto a PDFTemplate row
                           (uploaded PDF + placed fields from Template Builder)"""
    __tablename__ = "report_templates"
    id              = Column(Integer, primary_key=True)
    name            = Column(String(200), nullable=False)
    slug            = Column(String(100), unique=True, nullable=False)
    description     = Column(String(500))
    is_active       = Column(Boolean, default=True)
    kind            = Column(String(20), default="html", nullable=False)  # 'html' | 'pdf_overlay'
    pdf_template_id = Column(Integer, ForeignKey("pdf_templates.id"), nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    pdf_template    = relationship("PDFTemplate", foreign_keys=[pdf_template_id])


class TrailerGroup(Base):
    """A logical group of trailer types that share a default report template
    (e.g. all EXPLOSIVE bodies). Decoupled from trailer name so renames don't
    break the binding."""
    __tablename__ = "trailer_groups"
    id                 = Column(Integer, primary_key=True)
    name               = Column(String(200), unique=True, nullable=False)
    description        = Column(String(500))
    report_template_id = Column(Integer, ForeignKey("report_templates.id"), nullable=True)
    created_at         = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    report_template = relationship("ReportTemplate", foreign_keys=[report_template_id])
    trailer_types   = relationship("TrailerType", back_populates="group", foreign_keys="TrailerType.group_id")


class OrphanedTemplateAssignment(Base):
    """Survives delete/reimport: when a trailer with a group/override is
    deleted, we archive the binding here keyed by name. On the next import
    matching that name, the user is prompted to restore it."""
    __tablename__ = "orphaned_template_assignments"
    id                          = Column(Integer, primary_key=True)
    trailer_name                = Column(String(300), nullable=False)
    group_id                    = Column(Integer, ForeignKey("trailer_groups.id"), nullable=True)
    override_report_template_id = Column(Integer, ForeignKey("report_templates.id"), nullable=True)
    archived_at                 = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserSession(Base):
    """DB-backed session record — shared across all Passenger worker processes.
    Replaces the in-memory dict so sessions survive worker restarts."""
    __tablename__ = "user_sessions"
    id           = Column(String(36),  primary_key=True)   # UUID session_id cookie
    user_id      = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role         = Column(String(20))
    csrf_token   = Column(String(64))
    login_at     = Column(DateTime(timezone=True))
    last_seen_at = Column(DateTime(timezone=True))
    expires_at   = Column(DateTime(timezone=True))


class BOMSection(Base):
    """Registry of BOM section names (Column B headings from the Excel sheet).
    Auto-populated by imports; can also be managed manually via the admin UI."""
    __tablename__ = "bom_sections"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    sort_order = Column(Integer, default=0)
    multiplier = Column(Float, default=1.0)  # e.g. 2.0 for SIDES (two sides of a trailer)
    # Body Configurator Phase 2: section ownership by an option (master row).
    # When set, the section's items only render when that master is selected.
    # Lets a single option own multiple sections (e.g. DRD master owning both
    # "DRD" and "DRD DOOR FITTINGS"), which BodyOptionGroup.bom_section_id (1:1)
    # could not express.
    body_option_master_id = Column(Integer, ForeignKey("bill_of_materials.id", ondelete="SET NULL"), nullable=True)
    # Unassigned-tray timestamp. NULL = section is live; non-NULL = section is in
    # the Unassigned tray (items still in DB, but excluded from costing until the
    # user restores it to a group/option).
    archived_at = Column(DateTime, nullable=True)
    # Non-standard / opt-in sections (e.g. EXTRAS, OPTIONAL EXTRAS). When True:
    # admin UI styles section header + dropdown entry in red with a
    # "Non Standard items" tooltip; on Costings 1 & 2 the section is greyed out
    # by default and only contributes to the total when the user ticks it.
    is_optional = Column(Boolean, default=False, nullable=False)


class RepairTemplate(Base):
    """A reusable bundle of repair lines (v1.50 P3, migration 0044).

    SHARED TEAM-WIDE and SOFT-RETIRED (retired_at NULL = active), never hard
    deleted. Stores the ITEM LIST + DEFAULT QUANTITIES only — NEVER prices:
    a line's price resolves live from the materials master at the moment of
    use, so a template cannot quote a stale price."""
    __tablename__ = "repair_templates"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(120), nullable=True)   # username snapshot (house audit idiom)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String(120), nullable=True)
    retired_at = Column(DateTime(timezone=True), nullable=True, index=True)
    retired_by = Column(String(120), nullable=True)
    lines = relationship("RepairTemplateLine", back_populates="template",
                         cascade="all, delete-orphan",
                         order_by="RepairTemplateLine.sort_order")


class RepairTemplateLine(Base):
    """One line of a repair template. kind='stock' is a material REFERENCE
    (priced live at every use); kind='free_hand' is description + qty + unit
    with the price typed at use time. material_id on a free_hand line is
    provenance metadata from a body-category pull — it lets the expand offer a
    live list price, it never makes the line a catalogue row."""
    __tablename__ = "repair_template_lines"
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("repair_templates.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    kind = Column(String(16), nullable=False, default="free_hand")  # 'stock' | 'free_hand'
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="SET NULL"), nullable=True)
    description = Column(String(200), nullable=False)
    qty = Column(Float, nullable=True)
    unit = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    origin = Column(String(200), nullable=True)   # body-category chip, e.g. "SIDES"
    template = relationship("RepairTemplate", back_populates="lines")
    material = relationship("Material")


class BodyOptionGroup(Base):
    """Global registry of body-option zone names (FRONT, SIDES, DRD, SRD …).
    Auto-populated from imports and Body Designer saves."""
    __tablename__ = "body_option_groups"
    id             = Column(Integer, primary_key=True)
    name           = Column(String(100), unique=True, nullable=False)
    sort_order     = Column(Integer, default=0)
    bom_section_id = Column(Integer, ForeignKey("bom_sections.id"), nullable=True)
    # Configurator v2 — when this flag group is "nested" under a specific
    # choice-gate option, this points at the option's master row. The tree
    # builder then renders the flag group inline under that option instead
    # of as a top-level group. NULL = unlinked (top-level behaviour).
    parent_option_master_id = Column(Integer, ForeignKey("bill_of_materials.id"), nullable=True)
    subgroups      = relationship("BodyOptionSubgroup", back_populates="group",
                                  cascade="all, delete-orphan")
    bom_section    = relationship("BOMSection", foreign_keys="[BodyOptionGroup.bom_section_id]")


class BodyOptionSubgroup(Base):
    """Radio-group labels within a body-option zone (INSULATION, PLYWOOD …)."""
    __tablename__ = "body_option_subgroups"
    id         = Column(Integer, primary_key=True)
    group_id   = Column(Integer, ForeignKey("body_option_groups.id"), nullable=False)
    name       = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0)
    group      = relationship("BodyOptionGroup", back_populates="subgroups")
    __table_args__ = (UniqueConstraint('group_id', 'name', name='uq_bog_sub'),)


class SapItemCode(Base):
    """SAP material master — sourced from FORMULAS 2018.xls 'SAP ITEM CODES' sheet.
    Stores the last purchase price per item code; linked from SkinFormulaIngredient."""
    __tablename__ = "sap_item_codes"
    id               = Column(Integer, primary_key=True)
    item_code        = Column(String(200), unique=True, nullable=False)
    description      = Column(String(500))
    last_purch_price = Column(Float, default=0.0)
    is_active        = Column(Boolean, default=True)
    ingredients      = relationship("SkinFormulaIngredient", back_populates="sap_item")


class SkinFormulaIngredient(Base):
    """Ingredient used in fiberglass skin lamination recipes.
    Not in the materials catalogue — standalone pricing records."""
    __tablename__ = "skin_formula_ingredients"
    id               = Column(Integer, primary_key=True)
    name             = Column(String(200), unique=True, nullable=False)
    sap_code         = Column(String(100))
    sap_item_code_id = Column(Integer, ForeignKey("sap_item_codes.id", ondelete="SET NULL"), nullable=True)
    price_standard   = Column(Float, default=0.0)
    price_kzn        = Column(Float, default=0.0)
    is_active        = Column(Boolean, default=True)
    sort_order       = Column(Integer, default=0)
    items            = relationship("SkinFormulaItem", back_populates="ingredient")
    sap_item         = relationship("SapItemCode", back_populates="ingredients")


class TapingBlock(Base):
    """A taping block assembly recipe (e.g. 'TAPING BLOCK 200MM').
    Cost per block = Σ(item.m2 × item.price_per_unit × item.quantity)."""
    __tablename__ = "taping_blocks"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(200), unique=True, nullable=False)
    description = Column(String(500))
    size_mm     = Column(Integer, nullable=True)   # 200 or 250
    is_active   = Column(Boolean, default=True)
    sort_order  = Column(Integer, default=0)
    items       = relationship("TapingBlockItem", back_populates="block",
                               cascade="all, delete-orphan", order_by="TapingBlockItem.sort_order")
    bom_items   = relationship("BillOfMaterial", back_populates="taping_block")


class TapingBlockItem(Base):
    """One component line in a taping block recipe.
    line_cost = m2 × price_per_unit × quantity  (quantity=0 excludes the line)."""
    __tablename__ = "taping_block_items"
    id              = Column(Integer, primary_key=True)
    block_id        = Column(Integer, ForeignKey("taping_blocks.id"), nullable=False)
    item_name       = Column(String(200), nullable=False)
    sap_code        = Column(String(100))
    sap_item_code_id= Column(Integer, ForeignKey("sap_item_codes.id", ondelete="SET NULL"), nullable=True)
    length          = Column(Float, default=0.0)
    width           = Column(Float, default=0.0)
    m2              = Column(Float, default=0.0)
    price_per_unit  = Column(Float, default=0.0)   # price per m²
    # 'standard' = use price_per_unit; 'sap' = use sap_item.last_purch_price
    price_source    = Column(String(10), default="standard", nullable=False)
    quantity        = Column(Float, default=1.0)    # set to 0 to zero out line
    sort_order      = Column(Integer, default=0)
    block           = relationship("TapingBlock", back_populates="items")
    sap_item        = relationship("SapItemCode")


class FloorPlate(Base):
    """An SRD floor plate assembly from FORMULAS 2018.xls 'SRD FLOOR PLATE' sheet.
    Cost = Σ(item.m2 × item.price_per_unit × item.quantity) across left + right sides."""
    __tablename__ = "floor_plates"
    id            = Column(Integer, primary_key=True)
    name          = Column(String(200), unique=True, nullable=False)
    description   = Column(String(500))
    is_active     = Column(Boolean, default=True)
    sort_order    = Column(Integer, default=0)
    price_formula = Column(Text, nullable=True)   # JSON: [{"op":"/","val":12},{"op":"/","val":2.44}]
    items         = relationship("FloorPlateItem", back_populates="plate",
                                 cascade="all, delete-orphan", order_by="FloorPlateItem.sort_order")
    bom_items     = relationship("BillOfMaterial", back_populates="floor_plate")


class FloorPlateItem(Base):
    """One component line in a floor plate assembly.
    side = 'left' (structural plate/hardware) or 'right' (plybeam picture frame).
    line_cost = m2 × price_per_unit × quantity  (quantity=0 excludes the line)."""
    __tablename__ = "floor_plate_items"
    id               = Column(Integer, primary_key=True)
    plate_id         = Column(Integer, ForeignKey("floor_plates.id"), nullable=False)
    side             = Column(String(10), default="left", nullable=False)   # 'left' | 'right'
    item_name        = Column(String(200), nullable=False)
    sap_code         = Column(String(100))
    sap_item_code_id = Column(Integer, ForeignKey("sap_item_codes.id", ondelete="SET NULL"), nullable=True)
    length           = Column(Float, default=0.0)
    width            = Column(Float, default=0.0)
    m2               = Column(Float, default=0.0)
    price_per_unit   = Column(Float, default=0.0)
    price_source     = Column(String(10), default="standard", nullable=False)
    quantity         = Column(Float, default=1.0)
    sort_order       = Column(Integer, default=0)
    plate            = relationship("FloorPlate", back_populates="items")
    sap_item         = relationship("SapItemCode")


class MountingCleat(Base):
    """A mounting cleat / fish plate / bracket assembly from FORMULAS 2018.xls 'MOUNTING CLEATS'.
    group = 'MOUNTING CLEATS' | 'FISH PLATES' | 'MOUNTING BRACKETS'
    Cost = Σ(item.m2 × item.price_per_unit × item.quantity)."""
    __tablename__ = "mounting_cleats"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(200), unique=True, nullable=False)
    group       = Column(String(100), nullable=False)  # category within the sheet
    description = Column(String(500))
    is_active   = Column(Boolean, default=True)
    sort_order  = Column(Integer, default=0)
    items       = relationship("MountingCleatItem", back_populates="cleat",
                               cascade="all, delete-orphan", order_by="MountingCleatItem.sort_order")
    bom_items   = relationship("BillOfMaterial", back_populates="mounting_cleat")


class MountingCleatItem(Base):
    """One component line in a mounting cleat assembly."""
    __tablename__ = "mounting_cleat_items"
    id               = Column(Integer, primary_key=True)
    cleat_id         = Column(Integer, ForeignKey("mounting_cleats.id"), nullable=False)
    item_name        = Column(String(200), nullable=False)
    sap_code         = Column(String(100))
    sap_item_code_id = Column(Integer, ForeignKey("sap_item_codes.id", ondelete="SET NULL"), nullable=True)
    length           = Column(Float, default=0.0)
    width            = Column(Float, default=0.0)
    m2               = Column(Float, default=0.0)
    price_per_unit   = Column(Float, default=0.0)
    price_source     = Column(String(10), default="standard", nullable=False)
    quantity         = Column(Float, default=1.0)
    sort_order       = Column(Integer, default=0)
    cleat            = relationship("MountingCleat", back_populates="items")
    sap_item         = relationship("SapItemCode")


class SkinFormula(Base):
    """A named fiberglass skin lamination recipe (e.g. '450CSM-450').
    Cost per m² = Σ(ingredient.price_X × item.qty_per_m2) for the chosen region."""
    __tablename__ = "skin_formulas"
    id          = Column(Integer, primary_key=True)
    name        = Column(String(200), unique=True, nullable=False)
    description = Column(String(500))
    is_active   = Column(Boolean, default=True)
    sort_order  = Column(Integer, default=0)
    items       = relationship("SkinFormulaItem", back_populates="formula",
                               cascade="all, delete-orphan", order_by="SkinFormulaItem.sort_order")
    bom_items   = relationship("BillOfMaterial", back_populates="skin_formula")


class SkinFormulaItem(Base):
    """One ingredient line in a skin formula with quantity per m²."""
    __tablename__ = "skin_formula_items"
    id            = Column(Integer, primary_key=True)
    formula_id    = Column(Integer, ForeignKey("skin_formulas.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("skin_formula_ingredients.id"), nullable=False)
    qty_per_m2    = Column(Float, nullable=False)
    qty_formula   = Column(String(200), nullable=True)   # raw expression, e.g. "12/6" or "2*3.14"
    sort_order    = Column(Integer, default=0)
    # 'standard' = use ingredient.price_standard
    # 'sap'      = use ingredient.sap_item.last_purch_price
    price_source  = Column(String(10), default="standard", nullable=False)
    formula       = relationship("SkinFormula", back_populates="items")
    ingredient    = relationship("SkinFormulaIngredient", back_populates="items")


class BomSnapshot(Base):
    """Point-in-time snapshot of a body type's BOM costs."""
    __tablename__ = "bom_snapshots"
    id              = Column(Integer, primary_key=True)
    branch_id       = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)  # WO v4.12 multi-branch
    trailer_type_id = Column(Integer, ForeignKey("trailer_types.id"), nullable=False)
    source          = Column(String(10), nullable=False)   # 'app' or 'excel'
    label           = Column(String(200))                  # e.g. "May 2026 pricing"
    source_file     = Column(String(500))                  # original filename (Excel snapshots)
    dims_json       = Column(Text)                         # JSON of dims used (app snapshots)
    snapshot_date   = Column(String(10), nullable=False)   # YYYY-MM-DD
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_stale        = Column(Boolean, default=False)  # True after a price edit — pending re-capture
    is_pinned_baseline = Column(Boolean, default=False)  # One per body type — the approved reference
    trailer_type    = relationship("TrailerType")
    items           = relationship("BomSnapshotItem", back_populates="snapshot",
                                   cascade="all, delete-orphan", order_by="BomSnapshotItem.sort_order")


class ConfiguratorSnapshot(Base):
    """Point-in-time snapshot of a trailer's Body Configurator gating state.
    Stores everything needed to restore: section ownership/archived flags, master
    rows' selection fields, item bom_conditions, and body-option-group naming."""
    __tablename__ = "configurator_snapshots"
    id              = Column(Integer, primary_key=True)
    branch_id       = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)  # WO v4.12 multi-branch
    trailer_type_id = Column(Integer, ForeignKey("trailer_types.id"), nullable=False)
    name            = Column(String(200), nullable=False)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_by      = Column(String(100), nullable=True)
    payload         = Column(_BigJson, nullable=False)
    trailer_type    = relationship("TrailerType")


class ConfiguratorDraft(Base):
    """Server-persisted visual-configurator tree for one trailer. The JSON
    payload is the same draft the settings page previously kept only in browser
    localStorage; persisting it here lets the costings page apply the config on
    every browser/device, and it survives cache clears."""
    __tablename__ = "configurator_drafts"
    id              = Column(Integer, primary_key=True)
    branch_id       = Column(Integer, ForeignKey("branches.id"), nullable=True, index=True)  # WO v4.12 multi-branch
    trailer_type_id = Column(Integer, ForeignKey("trailer_types.id"), unique=True, nullable=False)
    payload         = Column(_BigJson, nullable=False)
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    updated_by      = Column(String(100), nullable=True)
    trailer_type    = relationship("TrailerType")


class ConfiguratorDraftSnapshot(Base):
    """Point-in-time backup of a ConfiguratorDraft payload for a single trailer.
    Distinct from ConfiguratorSnapshot (which captures BOM schema state) —
    this stores only the visual-configurator draft tree the Settings page edits.
    Many snapshots per trailer; users capture from the Settings page and restore
    to roll the Explorer tree back to a known-good state."""
    __tablename__ = "configurator_draft_snapshots"
    id              = Column(Integer, primary_key=True)
    trailer_type_id = Column(Integer, ForeignKey("trailer_types.id"), nullable=False, index=True)
    label           = Column(String(255), nullable=False)
    payload         = Column(_BigJson, nullable=False)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_by      = Column(String(100), nullable=True)
    trailer_type    = relationship("TrailerType")


class BomSnapshotItem(Base):
    __tablename__ = "bom_snapshot_items"
    id          = Column(Integer, primary_key=True)
    snapshot_id = Column(Integer, ForeignKey("bom_snapshots.id"), nullable=False)
    category    = Column(String(200), nullable=False)
    item_name   = Column(String(500), nullable=False)
    formula     = Column(Text)
    quantity    = Column(Float)
    unit_price  = Column(Float)
    total       = Column(Float, nullable=False)
    sort_order  = Column(Integer, default=0)
    bom_id      = Column(Integer)  # FK to bill_of_materials.id (app snapshots only)
    snapshot    = relationship("BomSnapshot", back_populates="items")


class ValidatedReference(Base):
    """A costing Nadie has VALIDATED (balanced against her Excel, or approved).

    Deliberately NOT related to the admin-level BomSnapshot feature above — this
    is a thin POINTER layer over saved costings (WO v1.45, migration 0039). The
    costing record already holds dims, body options, overrides and category
    totals in result_json.input_state (v1.39.9), so nothing is copied here: just
    the pointer, Nadie's label, and the fingerprint that makes exact-configuration
    matching a single indexed lookup.

    `active` is a SOFT retire — retired references stop matching and leave the
    recall dropdown, but the row (and its audit trail) is never deleted.
    """
    __tablename__ = "validated_references"
    id                 = Column(Integer, primary_key=True)
    calculation_id     = Column(Integer, ForeignKey("calculations.id", ondelete="CASCADE"),
                                nullable=False)
    label              = Column(String(120), nullable=False)
    # Indexes are owned by migration 0039 (ix_validated_refs_fingerprint,
    # ix_validated_refs_trailer_active, uq_validated_refs_active_calc) — NOT
    # declared here, so a model-driven create can never add a second, duplicate
    # index under SQLAlchemy's auto-generated name.
    config_fingerprint = Column(String(64), nullable=False)
    trailer_type_id    = Column(Integer, ForeignKey("trailer_types.id"), nullable=False)
    # Display-name snapshot at write time (ADR 0016 / chassis_records.edited_by_name).
    created_by         = Column(String(100), nullable=True)
    created_at         = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    active             = Column(Boolean, nullable=False, default=True)
    calculation        = relationship("CalculationRecord")
    trailer_type       = relationship("TrailerType")


class HelpRequestLog(Base):
    """One row per AI Help assistant request. Lightweight cost/usage telemetry.
    Captures token usage so admins can see the running cost of the feature.
    Tool-call metadata is summarised (count + names) — full tool I/O is NOT
    persisted to avoid leaking material/customer data into a log table."""
    __tablename__ = "help_request_log"
    id              = Column(Integer, primary_key=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    model           = Column(String(64))
    input_tokens    = Column(Integer, default=0)
    output_tokens   = Column(Integer, default=0)
    cached_tokens   = Column(Integer, default=0)  # cache_read_input_tokens
    cache_write_tokens = Column(Integer, default=0)  # cache_creation_input_tokens
    ms_elapsed      = Column(Integer, default=0)
    page            = Column(String(255), nullable=True)   # window.location.pathname at the time of asking
    tool_calls      = Column(Integer, default=0)
    tool_names      = Column(String(500), nullable=True)   # comma-separated names of tools invoked
    finish_reason   = Column(String(32), nullable=True)    # 'end_turn' | 'max_tokens' | 'tool_use' | 'error' | ...
    error           = Column(String(500), nullable=True)


def init_db():
    """Seed built-in defaults only. Schema/DDL is owned by Alembic — run
    `alembic upgrade head` before starting the app. (create_all() was removed in
    the unified monorepo, WO v4.12; the orphaned legacy SQLite/MySQL
    _run_migrations() body — dead code since that import — was DELETED in
    v1.40.9, its three still-relevant bootstraps rewired below.)"""
    _seed_defaults()
    # v1.40.6 — the permission-catalogue bootstrap MUST run on every boot: the v4.12
    # unification orphaned _run_migrations() (no call sites) and with it the
    # _bootstrap_permissions() call, so the "catalogue tops up any environment on
    # boot" promise (the 6-Jul prod-permissions lesson, comment at the MES-keys
    # block) silently stopped being true. Nobody noticed because every pre-existing
    # key is ALSO seeded by a migration; the admin.* page keys are the first
    # catalogue-only family. Idempotent + additive; never deletes or downgrades.
    import logging as _logging
    _blog = _logging.getLogger("burtcost.bootstrap")
    try:
        _bootstrap_permissions()
    except Exception as e:  # noqa: BLE001 — a bootstrap failure must not block boot
        _blog.error("PERMISSION BOOTSTRAP FAILED: %s: %s", type(e).__name__, str(e)[:300], exc_info=True)
    # v1.40.9 — the other two survivors of the dead _run_migrations() (orphaned since the
    # v4.12 unification import, deleted in this release): fresh environments need the
    # report templates (quote PDFs resolve against them) and the chassis option/constant
    # catalogues (the chassis-cost calculator). Both are internally idempotent; live DBs
    # already carry the rows, so boots there are no-ops.
    try:
        _bootstrap_report_templates()
    except Exception as e:  # noqa: BLE001
        _blog.error("REPORT-TEMPLATE BOOTSTRAP FAILED: %s: %s", type(e).__name__, str(e)[:300], exc_info=True)
    try:
        _bootstrap_chassis()
    except Exception as e:  # noqa: BLE001
        _blog.error("CHASSIS BOOTSTRAP FAILED: %s: %s", type(e).__name__, str(e)[:300], exc_info=True)


def _seed_defaults():
    """Ensure built-in global variables exist on first run."""
    from sqlalchemy.orm import Session as _Session
    with _Session(engine) as session:
        try:
            exists = session.query(GlobalVariable).filter_by(name="Waste").first()
            if not exists:
                session.add(GlobalVariable(name="Waste", value=0.05,
                                           description="Standard waste/overlap allowance (metres)"))
                session.commit()
        except Exception:
            session.rollback()


def _bootstrap_report_templates():
    """Seed developer-built ReportTemplates + TrailerGroups on first run, and
    auto-bind matching trailers to their group by name keyword. Idempotent."""
    # (slug, template_name, description, group_name, group_description, name_match)
    SEEDS = [
        ("explosive_quote", "EXPLOSIVE Body Quotation",
         "IceCold EXPLOSIVE-range quote (HTML+WeasyPrint).",
         "EXPLOSIVE", "EXPLOSIVE-range trailer bodies (auto-created).",
         "EXPLOSIVE"),
        # Match on "ORANGE" so both RHINORANGE and RHEINORANGE spellings bind
        # before the broader FREEZER seed claims them.
        ("rhinorange_quote", "RHINORANGE Body Quotation",
         "IceCold RHINORANGE Freezer-range quote (HTML+WeasyPrint).",
         "RHINORANGE", "RHINORANGE Freezer trailer bodies (auto-created).",
         "ORANGE"),
        # Match on "MEAT" so meathanger trailers bind before the broader
        # FREEZER seed claims them.
        ("meathanger_quote", "MEATHANGER Body Quotation",
         "IceCold MEATHANGER-range quote (HTML+WeasyPrint).",
         "MEATHANGER", "MEATHANGER-range trailer bodies (auto-created).",
         "MEAT"),
        ("freezer_quote", "FREEZER Body Quotation",
         "IceCold FREEZER-range quote (HTML+WeasyPrint).",
         "FREEZER", "FREEZER-range trailer bodies (auto-created).",
         "FREEZER"),
    ]
    db = SessionLocal()
    try:
        from sqlalchemy import func as _fn
        for slug, tname, tdesc, gname, gdesc, match in SEEDS:
            tmpl = db.query(ReportTemplate).filter_by(slug=slug).first()
            if not tmpl:
                tmpl = ReportTemplate(name=tname, slug=slug, description=tdesc, is_active=True)
                db.add(tmpl); db.flush()
                print(f"Seeded ReportTemplate: {slug} (id={tmpl.id})")

            grp = db.query(TrailerGroup).filter_by(name=gname).first()
            if not grp:
                grp = TrailerGroup(name=gname, description=gdesc, report_template_id=tmpl.id)
                db.add(grp); db.flush()
                print(f"Seeded TrailerGroup: {gname} (id={grp.id})")
            elif grp.report_template_id is None:
                grp.report_template_id = tmpl.id

            unassigned = db.query(TrailerType).filter(
                TrailerType.is_active == True,
                TrailerType.group_id.is_(None),
                _fn.upper(TrailerType.name).like(f"%{match}%"),
            ).all()
            for tt in unassigned:
                tt.group_id = grp.id
            if unassigned:
                print(f"Bound {len(unassigned)} {match} trailer(s) to group.")

        db.commit()
    finally:
        db.close()


# Authoritative permission catalogue. Adding/removing names here drives the
# admin UI — runtime checks read from the DB so renames must come with a
# migration of stale rows. (name, description, category, default_roles)
PERMISSION_CATALOGUE = [
    # ── Data visibility ─────────────────────────────────────────────────────
    ("bom.view_prices",   "View unit prices and line costs on results page",   "data",    {"admin", "full"}),
    ("bom.view_full_cost","View grand total / cost-per-m² summary",            "data",    {"admin", "full"}),
    # ── Exports / printing ──────────────────────────────────────────────────
    ("export.excel",      "Download cost breakdown as Excel",                  "exports", {"admin", "full"}),
    ("export.pdf",        "Download cost breakdown as PDF",                    "exports", {"admin", "full"}),
    ("export.word",       "Download cost breakdown as Word",                   "exports", {"admin", "full"}),
    ("quote.generate",    "Generate customer quote PDF for a costing",         "exports", {"admin", "full", "user"}),
    # ── Menu / page access ──────────────────────────────────────────────────
    ("menu.calculator",   "Access the costing calculator",                     "menu",    {"admin", "full", "user"}),
    ("menu.dashboard",    "Access the dashboard / saved costings list",        "menu",    {"admin", "full", "user"}),
    ("menu.materials",    "Access Manage Materials admin page",                "menu",    {"admin", "full"}),
    ("menu.templates",    "Access Quote Templates admin page",                 "menu",    {"admin"}),
    ("menu.themes",       "Access Themes admin page",                          "menu",    {"admin"}),
    ("menu.customers",    "Access Customers admin page",                       "menu",    {"admin", "full"}),
    ("menu.import",       "Access Import from Excel page",                     "menu",    {"admin"}),
    ("menu.users",        "Access Users admin page",                           "menu",    {"admin"}),
    ("menu.devtools",     "Access Dev Tools page",                             "menu",    {"admin"}),
    ("menu.quote_numbering","Access Quote Numbering admin page",               "menu",    {"admin"}),
    ("menu.chassis",      "Access Chassis Options admin page",                "menu",    {"admin"}),
    ("menu.body_templates","Access Body Templates admin page",                "menu",    {"admin"}),
    ("menu.pricing_formulas","Access Pricing Formulas group (Floor Plates, Mounting Cleats, SAP Prices, Skin Formulas, Taping Blocks)", "menu", {"admin"}),
    # ── Dashboard widgets ───────────────────────────────────────────────────
    ("dashboard.approval_rate","View Approval Rate stats card on dashboard",  "data",    {"admin", "full"}),
    # ── Inline recipe editing ────────────────────────────────────────────────
    ("recipes.edit_inline",   "Edit skin formula / taping block prices directly from the calculator", "admin", {"admin"}),
    # v1.44 R1 (Nadie) — permanent BOM price saves from the costing calculator's
    # section-price modal (PUT /api/bom/{id}, price-only body). Granted to 'full'
    # so Internal Sales can maintain prices; every other admin-gated surface
    # stays admin-only. Admin passes via the code-level wildcard as usual.
    ("costings.price_master_edit", "Save permanent BOM price changes from the costing calculator", "admin", {"admin", "full"}),
    # v1.45 (Nadie) — mark a balanced costing as a VALIDATED REFERENCE and retire
    # one. Follows costings.price_master_edit verbatim: seeded {admin, full} so
    # Internal Sales owns its own reference library. READING them (the recall
    # dropdown, the drift warning) needs no key — any costings user gets those.
    ("costings.validated_refs_manage", "Mark a costing as a validated reference and retire references", "admin", {"admin", "full"}),
    # v1.50 (Michael, 20 Aug) — Internal Sales may SOFT-DELETE its own draft. Third
    # in the costings.* family and seeded {admin, full} for the same reason as the
    # two above: the work is Internal Sales' own, so the key belongs to the role.
    #
    # The key alone is NOT the whole gate. It opens the door; the route then
    # applies Michael's three conditions (own record, still pending, nothing
    # scheduled) on top of it, because "may delete drafts" and "may delete THIS
    # costing" are different questions. Admin keeps the code-level wildcard and so
    # keeps its existing unrestricted behaviour, unnarrowed.
    #
    # RESTORE deliberately has NO key: undelete is a correction, not a sales
    # action, and stays on require_admin.
    ("costings.delete_own_draft", "Soft-delete your own costing while it is still pending and unscheduled", "admin", {"admin", "full"}),
    # v1.50 P3 (Lezette) — create/edit/retire REUSABLE REPAIR TEMPLATES. Follows
    # costings.price_master_edit verbatim: seeded {admin, full} so repair
    # estimators own their own template library. USING a template needs no key —
    # any costings user may pull one into a repair.
    ("costings.repair_templates_manage", "Create, edit and retire reusable repair templates", "admin", {"admin", "full"}),
    # ── MES permission keys (v1.40.1) ────────────────────────────────────────
    # Mirrors the data inserts of migrations 0005 / 0013 / 0016 / 0017 / 0028
    # VERBATIM (names, descriptions, grants). Those migrations seed migrated DBs,
    # but a DB that missed their data inserts (prod, found 6 Jul 2026: the whole
    # 'mes' family absent -> admin's /api/session permission list lacked
    # planning.acknowledge, so the SPA locked the Acknowledge button even for
    # admin) never healed, because this catalogue-driven startup bootstrap only
    # knew the legacy costings keys. The catalogue is now the authoritative
    # superset: _bootstrap_permissions() tops up any environment on boot.
    # Admin has NO grant rows here by design — role 'admin' is a code-level
    # wildcard (deps.user_can) and /api/session returns the full catalogue for
    # admins (services/session.effective_permissions).
    ("production.accept",            "Accept a calculation into production",             "mes", {"sales"}),
    ("production.pre_job_card",      "Send the pre-job card",                            "mes", {"sales"}),
    ("production.signoff_sales",     "Sales pre-job sign-off",                           "mes", {"sales"}),
    ("production.signoff_production","Production pre-job sign-off",                      "mes", {"production"}),
    ("production.chassis_received",  "Confirm chassis received",                         "mes", {"production", "planner"}),
    ("planning.acknowledge",         "Acknowledge a job on the Planning Board",          "mes", {"production", "planner"}),
    ("planning.schedule",            "Schedule / move a job into a slot",                "mes", {"planner"}),
    ("planning.unschedule",          "Remove a job from a slot",                         "mes", {"planner"}),
    ("stores.count",                 "Record a stock cycle count",                       "mes", {"stores"}),
    ("stores.raise_discrepancy",     "Raise a stock discrepancy to Buying",              "mes", {"stores"}),
    ("buying.resolve_discrepancy",   "Resolve a stock discrepancy",                      "mes", {"buyer", "buyer_senior"}),
    ("buying.raise_pr",              "Raise a single PR",                                "mes", {"buyer", "buyer_senior"}),
    ("buying.defer_pr",              "Defer a PO suggestion",                            "mes", {"buyer", "buyer_senior"}),
    ("buying.override_supplier",     "Override the suggested supplier",                  "mes", {"buyer_senior"}),
    ("buying.bulk_raise",            "Bulk-raise PRs",                                   "mes", {"buyer_senior"}),
    ("chassis.create",               "Create a chassis record",                          "mes", {"planner"}),
    ("chassis.update",               "Edit a chassis record",                            "mes", {"planner", "production"}),
    ("chassis.vcl",                  "Capture a VCL (book-in) event",                    "mes", {"planner", "production"}),
    ("chassis.dcl",                  "Capture a DCL (dispatch) event",                   "mes", {"planner", "production"}),
    ("chassis.assembly_assign",      "Assign a chassis to an assembly bay (parking -> assembly)", "mes", {"planner", "production"}),
    ("prejob.create",                "Create + submit Pre-Job Cards (Internal Sales)",   "mes", {"sales", "full"}),
    ("prejob.signoff_sales",         "Sales Rep check sign-off on a Pre-Job Card",       "mes", {"sales", "full"}),
    ("prejob.signoff_planner",       "Planner check sign-off on a Pre-Job Card",         "mes", {"planner"}),
    ("qc.inspect",                   "Record QC inspection verdicts (Kenny's inbox + per-category)", "mes", {"qc_inspector", "planner", "production"}),
    ("qc.signoff",                   "Finalize a QC inspection sign-off (pass -> dispatch)",         "mes", {"qc_inspector"}),
    # ── SPA Admin (Master Data) page keys (Admin Master-Data WO, v1.40.6) ────
    # One stable key per admin menu item so the BA can box individual pages into
    # roles later. default_roles EMPTY by design: role 'admin' is the code-level
    # wildcard (deps.user_can) and needs no rows; nobody else sees an admin page
    # until a grant row is added. Today's only consumer is the SPA sidebar
    # visibility filter (AppDataContext denies unknown admin.* keys by default);
    # server-side require_perm enforcement per page is the future roles release.
    ("admin.health-check",          "Admin: Health Check dashboard",                  "admin", set()),
    ("admin.qc",                    "Admin: QC inspection screen",                    "admin", set()),
    ("admin.defect-categories",     "Admin: QC defect categories",                    "admin", set()),
    ("admin.spec-options",          "Admin: Spec options (DDM dropdowns)",            "admin", set()),
    ("admin.rules",                 "Admin: BOM rules",                               "admin", set()),
    ("admin.lookups",               "Admin: Rule lookups (spec -> SAP code)",         "admin", set()),
    ("admin.price-overrides",       "Admin: Price overrides",                         "admin", set()),
    ("admin.prejob-templates",      "Admin: Pre-Job templates",                       "admin", set()),
    ("admin.fridge-units",          "Admin: Fridge units",                            "admin", set()),
    ("admin.chassis-models",        "Admin: Chassis types",                           "admin", set()),
    ("admin.prejob-signoffs",       "Admin: Pre-Job sign-offs",                       "admin", set()),
    ("admin.customers",             "Admin: Customers + contacts",                    "admin", set()),
    ("admin.orphan-chassis",        "Admin: Find Orphan Chassis",                     "admin", set()),
    ("admin.merge-chassis",         "Admin: Merge Chassis",                           "admin", set()),
    ("admin.feedback",              "Admin: Feedback inbox",                          "admin", set()),
    ("admin.production-thresholds", "Admin: Production stage thresholds",             "admin", set()),
    # v1.41.0 §9 P1 — the FIRST admin.* key that is ALSO enforced server-side (the floor-reset
    # endpoint calls user_can directly): resetting the shared Production Flow floor is a
    # deliberate, journaled admin action (floor_events 'floor_reset'), never a /plan gesture.
    ("admin.floor-reset",           "Admin: Reset the Production Flow floor",         "admin", set()),
]


# Arbitrary but fixed key for the advisory lock below. The value is meaningless;
# it only has to be identical in every worker of every process on this database.
_PERM_BOOTSTRAP_LOCK_KEY = 852_144_001


def _bootstrap_permissions():
    """Idempotently seed the Permission catalogue and the default role grants.
    User-specific overrides are never touched here.

    Serialized across workers by a transaction-scoped advisory lock. Prod runs
    `uvicorn --workers 4` and every worker bootstraps at startup, so the plain
    read-then-insert below is a race: on 8 Aug 2026 a deploy adding two new keys
    had two workers pass the "does it exist?" check together, one insert won and
    the other died on `permissions_name_key`. The loser's WHOLE transaction rolled
    back — not just the duplicate row but the ROLE GRANTS it had queued — while the
    app still logged "Application startup complete", so the failure was invisible
    until someone read the journal. Both tables involved carry unique constraints
    (permissions.name, uq_role_perm), so both halves could race.

    The lock is held to COMMIT and released automatically, so a crashed worker
    cannot wedge the others. Whoever gets it first seeds; the rest then read a
    fully-populated table and no-op. Cost is a few hundred ms of serialization,
    once, at boot.
    """
    db = SessionLocal()
    try:
        # Postgres-only in this monorepo (see requirements.txt), but degrade
        # gracefully rather than break a future backend: without the lock the
        # logic is exactly what it was before — correct single-worker, racy
        # multi-worker — instead of failing outright.
        try:
            db.execute(_sa_text("SELECT pg_advisory_xact_lock(:k)"),
                       {"k": _PERM_BOOTSTRAP_LOCK_KEY})
        except Exception:  # noqa: BLE001 — non-postgres backend
            db.rollback()

        # 1) Ensure every catalogue entry exists / is up-to-date.
        existing = {p.name: p for p in db.query(Permission).all()}
        catalogue_names = {n for (n, _d, _c, _r) in PERMISSION_CATALOGUE}
        for name, desc, category, _roles in PERMISSION_CATALOGUE:
            p = existing.get(name)
            if not p:
                db.add(Permission(name=name, description=desc, category=category))
                print(f"Seeded Permission: {name}")
            else:
                # Refresh description/category in case the catalogue changed.
                if p.description != desc:
                    p.description = desc
                if p.category != category:
                    p.category = category
        db.flush()

        # Refresh map after possible inserts.
        all_perms = {p.name: p for p in db.query(Permission).all()}

        # 2) Ensure default role grants exist. We only add missing rows — never
        #    remove rows the admin may have customised. (Admin wildcards via code,
        #    so admin role defaults are still seeded as a hint for the UI.)
        for name, _desc, _cat, default_roles in PERMISSION_CATALOGUE:
            perm = all_perms.get(name)
            if not perm:
                continue
            for role in default_roles:
                exists = db.query(RolePermission).filter_by(
                    role=role, permission_id=perm.id
                ).first()
                if not exists:
                    db.add(RolePermission(role=role, permission_id=perm.id))

        db.commit()
    finally:
        db.close()


def _bootstrap_chassis():
    """Seed chassis_options + chassis_constants from the source Excel sheet.
    Idempotent — only inserts rows when a (kind+label+axle) or (category+name) is missing.
    Prices come straight from the workbook where they are literal; for items priced
    via external-workbook references (steel, running gear) we seed price=0 and the
    admin fills them in via the chassis admin page."""
    db = SessionLocal()
    try:
        OPTIONS = [
            ("suspension", "Henred Mechanical",       1, None, 29900,  10),
            ("suspension", "Henred Mechanical",       2, None, 59800,  11),
            ("suspension", "Henred Mechanical",       3, None, 90100,  12),
            ("suspension", "Weweler Air",             1, None, 43400,  20),
            ("suspension", "Weweler Air",             2, None, 86000,  21),
            ("suspension", "Weweler Air",             3, None, 128600, 22),
            ("suspension", "BPW Mechanical",          1, None, 0,      30),
            ("suspension", "BPW Mechanical",          2, None, 0,      31),
            ("suspension", "BPW Mechanical",          3, None, 0,      32),
            ("suspension", "BPW Air Drum",            1, None, 0,      40),
            ("suspension", "BPW Air Drum",            2, None, 0,      41),
            ("suspension", "BPW Air Drum",            3, None, 0,      42),
            ("suspension", "BPW Air Disc",            1, None, 0,      50),
            ("suspension", "BPW Air Disc",            2, None, 0,      51),
            ("suspension", "BPW Air Disc",            3, None, 0,      52),
            ("suspension", "SAF Air Drum",            1, None, 0,      60),
            ("suspension", "SAF Air Drum",            2, None, 0,      61),
            ("suspension", "SAF Air Drum",            3, None, 0,      62),
            ("suspension", "SAF Air Intradisc",       1, None, 0,      70),
            ("suspension", "SAF Air Intradisc",       2, None, 0,      71),
            ("suspension", "SAF Air Intradisc",       3, None, 0,      72),
            ("lifting_axle", "Henred Lifting Axle",   None, None, 0,   10),
            ("lifting_axle", "BPW Lifting Axle",      None, None, 0,   20),
            ("lifting_axle", "SAF Lifting Axle",      None, None, 0,   30),
            ("brake", "Haldex Mechanical",            1, None, 11507,  10),
            ("brake", "Haldex Mechanical",            2, None, 14880,  11),
            ("brake", "Haldex Mechanical",            3, None, 16870,  12),
            ("brake", "Haldex Air",                   1, None, 13941,  20),
            ("brake", "Haldex Air",                   2, None, 21280,  21),
            ("brake", "Haldex Air",                   3, None, 23770,  22),
            ("brake", "Wabco Mechanical",             1, None, 0,      30),
            ("brake", "Wabco Mechanical",             2, None, 0,      31),
            ("brake", "Wabco Mechanical",             3, None, 0,      32),
            ("brake", "Wabco Air ABS",                1, None, 0,      40),
            ("brake", "Wabco Air ABS",                2, None, 0,      41),
            ("brake", "Wabco Air ABS",                3, None, 0,      42),
            ("brake", "Wabco Air EBSE",               1, None, 0,      50),
            ("brake", "Wabco Air EBSE",               2, None, 0,      51),
            ("brake", "Wabco Air EBSE",               3, None, 0,      52),
            ("tyre", "12R 22.5",                      None, "dual",          3995, 10),
            ("tyre", "315R 22.5",                     None, "dual",          3725, 20),
            ("tyre", "385/65R22.5",                   None, "super_single",  4720, 30),
            ("rim", "12R Steel Rim",                  None, "dual",          1610, 10),
            ("rim", "12R Alu Rim",                    None, "dual",          3685, 20),
            ("rim", "Super Single Steel Rim",         None, "super_single",  1725, 30),
            ("rim", "Super Single Alu Rim",           None, "super_single",  4250, 40),
            ("rim", "Alcoa Alu Rim (Dura Bright)",    None, "super_single",  0,    50),
        ]
        for kind, label, axle_count, tyre_style, price, sort in OPTIONS:
            exists = db.query(ChassisOption).filter_by(
                kind=kind, label=label, axle_count=axle_count
            ).first()
            if not exists:
                db.add(ChassisOption(
                    kind=kind, label=label, axle_count=axle_count,
                    tyre_style=tyre_style, price=price, sort_order=sort, is_active=True
                ))

        CONSTANTS = [
            ("steel", "130x8 55C Flat Bar",                     4.0,  0,    0, 10),
            ("steel", "3mm Hot Rolled Sheet 1225x2450",         0,    1,    0, 20),
            ("steel", "5mm 350WA 3000x1500",                    0,    5,    0, 30),
            ("steel", "6mm 350WA 1250x2500",                    0,    1,    0, 40),
            ("steel", "8mm 350WA 1250x2500",                    0,    1,    0, 50),
            ("steel", "100x100x3 Square Tube",                  0,    3,    0, 60),
            ("steel", "120x55 RSC",                             0,    12,   0, 70),
            ("steel", "8mm Round Bar",                          0,    18,   0, 80),
            ("steel", "127x4.5 Round Tube",                     0,    1.5,  0, 90),
            ("steel", "219x4.5 Round Tube",                     0,    1.5,  0, 100),
            ("steel", "25mm Round Bar",                         0,    6,    0, 110),
            ("steel", "50x3 Round Tube",                        0,    6,    0, 120),
            ("running_gear", "JOST Landing Legs",               0,    1,    0, 10),
            ("running_gear", "1008 King Pin",                   0,    1,    0, 20),
            ("running_gear", "Electrical Loom",                 0,    1,    0, 30),
            ("running_gear", "Mudflaps",                        0,    1,    0, 40),
            ("running_gear", "Electrical Plugs",                0,    1,    0, 50),
            ("running_gear", "Chevron",                         0,    1,    0, 60),
            ("running_gear", "Reflexite Tape",                  2.0,  2.6,  0, 70),
            ("running_gear", "Paint",                           0,    1,    0, 80),
        ]
        for category, name, qpm, qc, price, sort in CONSTANTS:
            exists = db.query(ChassisConstant).filter_by(
                category=category, name=name
            ).first()
            if not exists:
                db.add(ChassisConstant(
                    category=category, name=name,
                    qty_per_metre=qpm, qty_constant=qc,
                    unit_price=price, sort_order=sort, is_active=True
                ))
        db.commit()
    finally:
        db.close()


def _bootstrap_skin_formulas():
    """Seed SkinFormulaIngredient and SkinFormula records from FORMULAS 2018.xls.
    Idempotent — only inserts when names are absent."""
    INGREDIENTS = [
        # (name, sap_code, price_standard, price_kzn, sort_order)
        ("59 GELCOAT",       "RES/GELCOAT/WHITE",     87.0,  46.87, 10),
        ("282 RESIN",        "RES/ORTHO_LAM/282",     44.05, 30.48, 20),
        ("450CSM",           "RES/CSM/450",           31.7,  20.72, 30),
        ("300CSM",           "RES/CSM/300",           28.5,  20.72, 40),
        ("M50 CATALYST 1",   "RES/BUTANOX/M50",      124.5,  46.3,  50),
        ("M50 CATALYST 2",   "RES/BUTANOX/M50",      124.5,  46.3,  60),
        ("M50 CATALYST",     "RES/BUTANOX/M50",      124.5,  46.3,  70),
        ("P939 GREY PIGMENT","RES/PIGMENT/GREY",      99.1,  75.69, 80),
        ("AEROSIL POWDER",   "RES/CABOSIL_FUME_SIL", 115.0,  78.0,  90),
        ("600TWIRL 300CSM",  "RES/TWIRL/300",         42.0,  42.0, 100),
    ]

    # (formula_name, description, sort_order, [(ingredient_name, qty_per_m2, item_sort), ...])
    FORMULAS = [
        ("450CSM-450", "Single skin 450 CSM laminate", 10, [
            ("59 GELCOAT",     0.75,  10),
            ("282 RESIN",      0.99,  20),
            ("450CSM",         0.45,  30),
            ("M50 CATALYST 1", 0.015, 40),
            ("M50 CATALYST 2", 0.044, 50),
        ]),
        ("450CSM-300", "Single skin 300 CSM laminate", 20, [
            ("59 GELCOAT",     0.75,   10),
            ("282 RESIN",      1.035,  20),
            ("300CSM",         0.45,   30),
            ("M50 CATALYST 1", 0.015,  40),
            ("M50 CATALYST 2", 0.046,  50),
        ]),
        ("900CSM-450-1", "Double skin 450 CSM interior sheet for RTT", 30, [
            ("59 GELCOAT",     0.75,  10),
            ("282 RESIN",      1.98,  20),
            ("450CSM",         0.9,   30),
            ("M50 CATALYST 1", 0.015, 40),
            ("M50 CATALYST 2", 0.044, 50),
        ]),
        ("600CSM-450", "Medium skin 450 CSM laminate", 40, [
            ("59 GELCOAT",     0.75,  10),
            ("282 RESIN",      1.32,  20),
            ("450CSM",         0.6,   30),
            ("M50 CATALYST 1", 0.015, 40),
            ("M50 CATALYST 2", 0.044, 50),
        ]),
        ("600CSM-300", "Medium skin 300 CSM laminate", 50, [
            ("59 GELCOAT",     0.75,    10),
            ("282 RESIN",      1.38,    20),
            ("300CSM",         0.6,     30),
            ("M50 CATALYST 1", 0.01125, 40),
            ("M50 CATALYST 2", 0.0345,  50),
        ]),
        ("1350CSM", "Heavy skin 450 CSM exterior sheet for RTT", 60, [
            ("59 GELCOAT",     0.75,  10),
            ("282 RESIN",      2.97,  20),
            ("450CSM",         1.35,  30),
            ("M50 CATALYST 1", 0.015, 40),
            ("M50 CATALYST 2", 0.044, 50),
        ]),
        ("900CSM-450-0", "Double skin 450 CSM exterior sheet", 70, [
            ("59 GELCOAT",     0.75,  10),
            ("282 RESIN",      1.98,  20),
            ("450CSM",         0.9,   30),
            ("M50 CATALYST 1", 0.015, 40),
            ("M50 CATALYST 2", 0.044, 50),
        ]),
        ("900CSM-300", "Double skin 300 CSM laminate", 80, [
            ("59 GELCOAT",     0.75,    10),
            ("282 RESIN",      2.07,    20),
            ("300CSM",         0.9,     30),
            ("M50 CATALYST 1", 0.01125, 40),
            ("M50 CATALYST 2", 0.0345,  50),
        ]),
        ("INTERNAL KICK PLATE LAMINATION", "Kick plate internal lamination with pigment", 90, [
            ("450CSM",            0.9,    10),
            ("282 RESIN",         1.98,   20),
            ("M50 CATALYST",      0.0396, 30),
            ("P939 GREY PIGMENT", 0.198,  40),
        ]),
        ("INTERNAL LAMINATION", "Internal surface lamination with 300 CSM", 100, [
            ("300CSM",            0.3,    10),
            ("282 RESIN",         0.72,   20),
            ("M50 CATALYST",      0.0144, 30),
            ("P939 GREY PIGMENT", 0.072,  40),
        ]),
        ("450 CSM ONLY", "450 CSM laminate without gelcoat", 110, [
            ("282 RESIN",      1.035,   10),
            ("450CSM",         0.45,    20),
            ("M50 CATALYST 1", 0.01125, 30),
            ("M50 CATALYST 2", 0.0345,  40),
        ]),
        ("FINAL COAT", "Final coat — resin, aerosil and pigment", 120, [
            ("282 RESIN",         0.7,  10),
            ("AEROSIL POWDER",    0.07, 20),
            ("P939 GREY PIGMENT", 0.07, 30),
        ]),
        ("COMBO FLOOR MATT", "Floor lamination with 600 Twirl 300 CSM", 130, [
            ("282 RESIN",       1.08,  10),
            ("600TWIRL 300CSM", 1.0,   20),
            ("M50 CATALYST 2",  0.018, 30),
        ]),
    ]

    db = SessionLocal()
    try:
        ing_map = {}
        for name, sap, std, kzn, sort in INGREDIENTS:
            ing = db.query(SkinFormulaIngredient).filter_by(name=name).first()
            if not ing:
                ing = SkinFormulaIngredient(
                    name=name, sap_code=sap, price_standard=std,
                    price_kzn=kzn, sort_order=sort, is_active=True
                )
                db.add(ing)
                db.flush()
                print(f"Seeded SkinFormulaIngredient: {name}")
            ing_map[name] = ing

        for fname, fdesc, fsort, fitems in FORMULAS:
            formula = db.query(SkinFormula).filter_by(name=fname).first()
            if not formula:
                formula = SkinFormula(
                    name=fname, description=fdesc, sort_order=fsort, is_active=True
                )
                db.add(formula)
                db.flush()
                for iname, qty, isort in fitems:
                    ing = ing_map.get(iname)
                    if ing:
                        db.add(SkinFormulaItem(
                            formula_id=formula.id,
                            ingredient_id=ing.id,
                            qty_per_m2=qty,
                            sort_order=isort,
                        ))
                print(f"Seeded SkinFormula: {fname}")

        db.commit()

        # Backfill price_source = 'sap' for formulas that use SAP LastPurPrc pricing.
        # Identified from FORMULA SKINS sheet: 900CSM-450-1 ingredient prices match
        # SAP LastPurPrc exactly. Others default to 'standard'.
        SAP_PRICED_FORMULAS = {"900CSM-450-1"}
        updated = 0
        for item in db.query(SkinFormulaItem).join(SkinFormula).filter(
            SkinFormula.name.in_(SAP_PRICED_FORMULAS),
            SkinFormulaItem.price_source != "sap",
        ).all():
            item.price_source = "sap"
            updated += 1
        if updated:
            db.commit()
            print(f"price_source backfill: set {updated} recipe rows to 'sap'")

    finally:
        db.close()


def _bootstrap_taping_blocks():
    """Seed TapingBlock and TapingBlockItem records from FORMULAS 2018.xls 'TAPING BLOCKS' sheet.
    Idempotent — skips blocks whose name already exists. Also backfills sap_item_code_id."""

    # (block_name, description, size_mm, sort_order,
    #  [(item_name, sap_code, length, width, m2, price_per_unit, quantity, sort_order), ...])
    BLOCKS = [
        ("TAPING BLOCK 200MM", "Standard taping block 200mm", 200, 10, [
            ("LVL BEAM",        "TIM/SOLID/152X50/5.4",      2.7,  0.2,   0.54,   68.0,    1.0, 10),
            ("GLUE",            "GLU/RIGIBOND5",             0.0,  0.0,   0.026,  28.583,  1.0, 20),
            ("4MM PLYWOOD",     "TIM/PE/1220X2440X04",       0.0,  0.0,   0.026,  71.477,  1.0, 30),
            ("GLUE X2",         "GLU/RIGIBOND5",             0.0,  0.0,   0.026,  28.583,  1.0, 40),
            ("130*8 FLAT BAR",  "STE/FL_BAR/130X08",         0.0,  0.0,   0.0,     0.0,   1.0, 50),
        ]),
        ("TAPING BLOCK 250MM", "Standard taping block 250mm", 250, 20, [
            ("LVL BEAM",        "TIM/SOLID/152X50/5.4",      2.7,  0.25,  0.675,  68.0,    1.0, 10),
            ("GLUE",            "GLU/RIGIBOND5",             0.0,  0.0,   0.026,  28.583,  1.0, 20),
            ("4MM PLYWOOD",     "TIM/PE/1220X2440X04",       0.0,  0.0,   0.026,  71.477,  1.0, 30),
            ("GLUE X2",         "GLU/RIGIBOND5",             0.0,  0.0,   0.026,  28.583,  1.0, 40),
            ("130*8 FLAT BAR",  "STE/FL_BAR/130X08",         0.0,  0.0,   0.0,     0.0,   1.0, 50),
        ]),
        ("CHEAP TAPPING BLOCK 200MM", "Cheap taping block 200mm", 200, 30, [
            ("130*19 SHATTER",  "TIM/PE/1220X2440X18",       0.0,  0.0,   0.026,  18.85,   1.0, 10),
            ("GLUE",            "GLU/RIGIBOND5",             0.0,  0.0,   0.026,  28.583,  1.0, 20),
        ]),
        ("CHEAP TAPPING BLOCK 250MM", "Cheap taping block 250mm", 250, 40, [
            ("130*19 SHATTER",  "TIM/PE/1220X2440X18",       0.0,  0.0,   0.0325, 725.0,   1.0, 10),
            ("GLUE",            "GLU/RIGIBOND5",             0.0,  0.0,   0.026,  28.583,  1.0, 20),
        ]),
        ("TIMBER ONLY TAPING BLOCK 200MM", "Timber only taping block 200mm", 200, 50, [
            ("130*50 TIMBER",   "TIM/SOLID/152X50/5.4",      0.0,  0.0,   0.026,  195.0,   1.0, 10),
            ("GLUE",            "GLU/RIGIBOND5",             0.0,  0.0,   0.026,  28.583,  1.0, 20),
            ("19MM PLYWOOD",    "TIM/PE/1220X2440X18",       0.0,  0.0,   0.026,  725.0,   1.0, 30),
        ]),
        ("TIMBER ONLY TAPING BLOCK 250MM", "Timber only taping block 250mm", 250, 60, [
            ("130*50 TIMBER",   "TIM/SOLID/152X50/5.4",      0.0,  0.0,   0.026,  195.0,   1.0, 10),
            ("GLUE",            "GLU/RIGIBOND5",             0.0,  0.0,   0.026,  28.583,  1.0, 20),
            ("19MM PLYWOOD",    "TIM/PE/1220X2440X18",       0.0,  0.0,   0.026,  725.0,   1.0, 30),
        ]),
    ]

    db = SessionLocal()
    try:
        sap_map = {r.item_code: r.id for r in db.query(SapItemCode).all()}

        for bname, bdesc, bsize, bsort, items in BLOCKS:
            block = db.query(TapingBlock).filter_by(name=bname).first()
            if not block:
                block = TapingBlock(
                    name=bname, description=bdesc, size_mm=bsize,
                    sort_order=bsort, is_active=True
                )
                db.add(block)
                db.flush()
                needs_items = True
            else:
                # Re-seed items if count doesn't match (guards against stale partial seeds)
                needs_items = len(block.items) != len(items)
                if needs_items:
                    for old in list(block.items):
                        db.delete(old)
                    db.flush()
            if needs_items:
                for iname, isap, ilen, iwid, im2, iprice, iqty, isort in items:
                    sap_id = sap_map.get(isap) if isap else None
                    db.add(TapingBlockItem(
                        block_id=block.id,
                        item_name=iname,
                        sap_code=isap or None,
                        sap_item_code_id=sap_id,
                        length=ilen,
                        width=iwid,
                        m2=im2,
                        price_per_unit=iprice,
                        quantity=iqty,
                        sort_order=isort,
                        price_source="standard",
                    ))
                print(f"Seeded TapingBlock items: {bname}")

        db.commit()

        # Backfill sap_item_code_id on any existing TapingBlockItem rows that have a sap_code.
        items_missing = db.query(TapingBlockItem).filter(
            TapingBlockItem.sap_code.isnot(None),
            TapingBlockItem.sap_item_code_id.is_(None),
        ).all()
        linked = 0
        for it in items_missing:
            sap_id = sap_map.get(it.sap_code.strip()) if it.sap_code else None
            if sap_id:
                it.sap_item_code_id = sap_id
                linked += 1
        if linked:
            db.commit()
            print(f"Linked {linked} TapingBlockItem rows to SAP item codes")

    finally:
        db.close()


def _bootstrap_floor_plates():
    """Seed FloorPlate assemblies from FORMULAS 2018.xls 'SRD FLOOR PLATE' sheet.
    Cols A-H → 4 structural/hardware assemblies.
    Cols J-O → 3 plybeam picture-frame assemblies (no SAP codes).
    Always re-seeds items for named plates so the data stays in sync with the sheet."""

    # (plate_name, description, sort_order,
    #  [(item_name, sap_code, length, width, m2, price_per_unit, quantity, sort_order), ...])
    # RESICHEM GLUE has no m² in the sheet; stored as m2=1.0, price=fixed assembly total.
    PLATES = [
        # ── Cols A-H: Structural Plate / Hardware ────────────────────────────
        ("2MM 3CR12", "Structural plate and hardware assembly", 10, [
            ("3MM 3CR12",          "STE-3C-1250X2500X2.0",  0.415, 0.8,  0.332,  3018.0,             1.0, 10),
            ("SILPLUS X-WHITE",    "SEA/TECTANE_WHITE",      0.0,   0.0,  0.25,   116.15,             1.0, 20),
            ("M8*150 GALV. BOLTS", "FAS/CUP_SQ/08X150",     0.0,   0.0,  3.0,    2.5,                1.0, 30),
            ("M8 FENDER WASHERS",  "FAS/FEN_W/08X040X3.0",  0.0,   0.0,  3.0,    0.2124,             1.0, 40),
            ("M8 NYLOCK NUTS",     "FAS/NYLOCK_NUT/08",     0.0,   0.0,  3.0,    0.3352,             1.0, 50),
        ]),
        ("3MM ALU BUFFER PLATE", "Structural plate and hardware assembly", 20, [
            ("3MM",                "STE-PLT-1250X2500X3.",   0.25,  0.2,  0.05,   3018.0,             1.0, 10),
            ("SILPLUS X-WHITE",    "SEA/TECTANE_WHITE",      0.0,   0.0,  0.1,    116.15,             1.0, 20),
            ("0661-0631 RIVETS",   "FAS/RIVET_LONG/0632",   0.0,   0.0,  4.0,    0.515,              1.0, 30),
        ]),
        ("D-RUBBER", "Structural plate and hardware assembly", 30, [
            ("1519 D-RUBBER",      "RUB/DOCK_FEND/1519",    0.05,  0.0,  0.05,   1353.3,             1.0, 10),
            ("3MM PLATE",          "STE-HRS-1225X2450X03",  0.15,  0.1,  0.015,  1145.56,            1.0, 20),
            ("3MM PLATE BRACKET",  "STE-HRS-1225X2450X03",  0.09,  0.1,  0.009,  1145.56,            1.0, 30),
            ("0661-0631 RIVETS",   "FAS/RIVET_LONG/0632",   0.0,   0.0,  4.0,    0.515,              1.0, 40),
        ]),
        ("CORNER GUSSETS", "Structural plate and hardware assembly", 40, [
            ("5MM PLATE",          "STE-M-1500X3000X05.0",  0.3,   0.15, 0.045,  1982.24,            1.0, 10),
        ]),
        # ── Cols J-O: Plybeam Picture Frame ──────────────────────────────────
        ("PLYBEAM PICTURE FRAME FOR BAKERY ROOFS", "Plybeam picture frame assembly", 50, [
            ("40MM STYRENE",       None, 2.44, 1.22, 2.9768, 79.57387127116365,  1.0, 10),
            ("4MM PHENO PLYWOOD",  None, 2.44, 1.22, 2.9768, 213.0,              1.0, 20),
            ("RESICHEM GLUE",      None, 0.0,  0.0,  1.0,    113.5711111111111,  1.0, 30),
        ]),
        ("PLYBEAM PICTURE FRAME FOR CHILLERS/FREEZER/MEAT BODY", "Plybeam picture frame assembly", 60, [
            ("58MM STYRENE",       None, 2.44, 1.22, 2.9768, 106.09849502821821, 1.0, 10),
            ("4MM PHENO PLYWOOD",  None, 2.44, 1.22, 2.9768, 213.0,              1.0, 20),
            ("RESICHEM GLUE",      None, 0.0,  0.0,  1.0,    113.5711111111111,  1.0, 30),
        ]),
        ("PLYBEAM PICTURE FRAME FOR CHILLERS/FREEZER/MEAT BODY ROOFS", "Plybeam picture frame assembly", 70, [
            ("94MM STYRENE",       None, 2.44, 1.22, 2.9768, 166.22097554420853, 1.0, 10),
            ("4MM PHENO PLYWOOD",  None, 2.44, 1.22, 2.9768, 213.0,              1.0, 20),
            ("RESICHEM GLUE",      None, 0.0,  0.0,  1.0,    113.5711111111111,  1.0, 30),
        ]),
    ]

    db = SessionLocal()
    try:
        sap_map = {r.item_code: r.id for r in db.query(SapItemCode).all()}

        for pname, pdesc, psort, items in PLATES:
            plate = db.query(FloorPlate).filter_by(name=pname).first()
            if not plate:
                plate = FloorPlate(
                    name=pname, description=pdesc,
                    sort_order=psort, is_active=True
                )
                db.add(plate)
                db.flush()
            else:
                plate.description = pdesc
                plate.sort_order  = psort
            # Always clear and re-seed items so data stays in sync with the sheet
            for old in list(plate.items):
                db.delete(old)
            db.flush()
            for iname, isap, ilen, iwid, im2, iprice, iqty, isort in items:
                sap_id = sap_map.get(isap) if isap else None
                db.add(FloorPlateItem(
                    plate_id=plate.id,
                    side="left",
                    item_name=iname,
                    sap_code=isap or None,
                    sap_item_code_id=sap_id,
                    length=ilen,
                    width=iwid,
                    m2=im2,
                    price_per_unit=iprice,
                    quantity=iqty,
                    sort_order=isort,
                    price_source="standard",
                ))
            print(f"Seeded FloorPlate: {pname}")

        db.commit()

        # Backfill sap_item_code_id on any existing FloorPlateItem rows.
        items_missing = db.query(FloorPlateItem).filter(
            FloorPlateItem.sap_code.isnot(None),
            FloorPlateItem.sap_item_code_id.is_(None),
        ).all()
        linked = 0
        for it in items_missing:
            sap_id = sap_map.get(it.sap_code.strip()) if it.sap_code else None
            if sap_id:
                it.sap_item_code_id = sap_id
                linked += 1
        if linked:
            db.commit()
            print(f"Linked {linked} FloorPlateItem rows to SAP item codes")

    finally:
        db.close()


def _bootstrap_mounting_cleats():
    """Seed MountingCleat assemblies from FORMULAS 2018.xls 'MOUNTING CLEATS' sheet.
    Cols A-G → MOUNTING CLEATS group (4 assemblies).
    Cols I-R → FISH PLATES group (2) and MOUNTING BRACKETS group (2).
    Always re-seeds items so data stays in sync with the sheet."""

    # (name, group, description, sort_order,
    #  [(item_name, sap_code, length, width, m2, price_per_unit, quantity, sort_order), ...])
    CLEATS = [
        # ── MOUNTING CLEATS group (cols A-G) ─────────────────────────────────
        ("TOP MOUNTING CLEAT", "MOUNTING CLEATS", "Top mounting cleat assembly", 10, [
            ("5MM PLATE",          "STE-M-1200X2500X05.0", 0.13, 0.13, 0.0169, 1982.24, 1.0, 10),
            ("50*10 FLAT BAR",     "STE/FL_BAR/050X10",    0.1,  0.0,  0.0,    0.0,     1.0, 20),
        ]),
        ("BOTTOM MOUNTING CLEAT", "MOUNTING CLEATS", "Bottom mounting cleat assembly", 20, [
            ("5MM PLATE",          "STE-M-1200X2500X05.0", 0.2,  0.13, 0.026,  1982.24, 1.0, 10),
            ("50*10 FLAT BAR",     "STE/FL_BAR/050X10",    0.1,  0.0,  0.0,    0.0,     1.0, 20),
            ("M12*40 H.T. BOLTS",  "FAS/HT_BOLT/12X040",  0.0,  0.0,  2.0,    7.5,     1.0, 30),
            ("M12 FLAT WASHER",    "FAS/FLAT_WASHER/12",   0.0,  0.0,  2.0,    0.3128,  1.0, 40),
            ("M12 NYLOCK",         "FAS/NYLOCK_NUT/12",    0.0,  0.0,  2.0,    0.8156,  1.0, 50),
        ]),
        ("SPRING MOUNTING CLEAT", "MOUNTING CLEATS", "Spring mounting cleat assembly", 30, [
            ("MOUNTING SPRING 16MM",   "FAS/M_SPRING/16",      0.0,  0.0,  1.0,    162.9,   1.0, 10),
            ("SP 200 MOUNTING WASHER", "FAS/M_WASHER",         0.0,  0.0,  1.0,    18.22,   1.0, 20),
            ("TOP+BOTTOM CLEAT",       "STE-M-1200X2500X05.0", 0.25, 0.13, 0.0325, 1982.24, 2.0, 30),
            ("100*70*8 FLAT BAR",      None,                   0.1,  0.07, 0.007,  79.83,   2.0, 40),
            ("M12*40 HT BOLTS",       "FAS/HT_BOLT/12X040",   0.0,  0.0,  4.0,    7.5,     1.0, 50),
            ("M12 FLAT WASHERS",      "FAS/FLAT_WASHER/12",   0.0,  0.0,  4.0,    0.3128,  1.0, 60),
            ("M12 NYLOCK NUTS",       "FAS/NYLOCK_NUT/12",    0.0,  0.0,  4.0,    0.8156,  1.0, 70),
            ("M 16*200 HT BOLT",      "FAS/HT_BOLT/16X200",   0.0,  0.0,  1.0,    33.22,   1.0, 80),
            ("M 16 NYLOCK NUT",       "FAS/NYLOCK_NUT/16",    0.0,  0.0,  1.0,    1.8212,  1.0, 90),
        ]),
        ("OFFSET WASHER", "MOUNTING CLEATS", "Offset washer — 522 cut per plate", 40, [
            ("4MM PLATE - 522 OUT OF A PLATE", None, 1.0, 1.0, 1.0, 1982.24, 1.0, 10),
        ]),
        # ── FISH PLATES group (cols I-R) ─────────────────────────────────────
        ("SMALL FISH PLATE", "FISH PLATES", "Small fish plate assembly", 50, [
            ("8MM PLATE",       "STE-M-1200X2500X08.0", 0.2,  0.16, 0.032,  1175.0, 1.0, 10),
            ("M12*40 HT BOLT",  "FAS/HT_BOLT/12X040",  0.0,  0.0,  2.0,    7.5,    1.0, 20),
            ("M12 NYLOCK NUT",  "FAS/FLAT_WASHER/12",  0.0,  0.0,  2.0,    0.8156, 1.0, 30),
            ("M12 FLAT WASHER", "FAS/NYLOCK_NUT/12",   0.0,  0.0,  2.0,    0.3128, 1.0, 40),
        ]),
        ("BIG FISH PLATE", "FISH PLATES", "Big fish plate assembly", 60, [
            ("8MM PLATE",       "STE-M-1200X2500X08.0", 0.25, 0.21, 0.0525, 1175.0, 1.0, 10),
            ("M12*40 HT BOLT",  "FAS/HT_BOLT/12X040",  0.0,  0.0,  2.0,    7.5,    1.0, 20),
            ("M12 NYLOCK NUT",  "FAS/FLAT_WASHER/12",  0.0,  0.0,  2.0,    0.8156, 1.0, 30),
            ("M12 FLAT WASHER", "FAS/NYLOCK_NUT/12",   0.0,  0.0,  2.0,    0.3128, 1.0, 40),
        ]),
        # ── MOUNTING BRACKETS group (cols I-R) ───────────────────────────────
        ("SMALL MOUNTING BRACKET 0.28x0.14", "MOUNTING BRACKETS", "Small mounting bracket assembly", 70, [
            ("4MM PLATE",      "STE-HRS-1225X2450X04", 0.28, 0.14, 0.0392, 665.1812080536913, 1.0, 10),
            ("OFFSET WASHER",  None,                   0.0,  0.0,  1.0,    0.0,               1.0, 20),
            ("M16*40 HT BOLT", "FAS/HT_BOLT/16X040S", 0.0,  0.0,  1.0,    7.5,               1.0, 30),
        ]),
        ("LARGE MOUNTING BRACKET 0.4x0.24", "MOUNTING BRACKETS", "Large mounting bracket assembly", 80, [
            ("4MM PLATE",      "STE-HRS-1225X2450X04", 0.4,  0.24, 0.096,  665.1812080536913, 1.0, 10),
            ("OFFSET WASHER",  None,                   0.0,  0.0,  2.0,    0.0,               1.0, 20),
            ("M16*40 HT BOLT", "FAS/HT_BOLT/16X040S", 0.0,  0.0,  2.0,    7.5,               1.0, 30),
        ]),
    ]

    db = SessionLocal()
    try:
        sap_map = {r.item_code: r.id for r in db.query(SapItemCode).all()}

        for name, group, desc, sort_order, items in CLEATS:
            cleat = db.query(MountingCleat).filter_by(name=name).first()
            if not cleat:
                cleat = MountingCleat(
                    name=name, group=group, description=desc,
                    sort_order=sort_order, is_active=True
                )
                db.add(cleat)
                db.flush()
            else:
                cleat.group       = group
                cleat.description = desc
                cleat.sort_order  = sort_order
            for old in list(cleat.items):
                db.delete(old)
            db.flush()
            for iname, isap, ilen, iwid, im2, iprice, iqty, isort in items:
                sap_id = sap_map.get(isap) if isap else None
                db.add(MountingCleatItem(
                    cleat_id=cleat.id,
                    item_name=iname,
                    sap_code=isap or None,
                    sap_item_code_id=sap_id,
                    length=ilen,
                    width=iwid,
                    m2=im2,
                    price_per_unit=iprice,
                    quantity=iqty,
                    sort_order=isort,
                    price_source="standard",
                ))
            print(f"Seeded MountingCleat: {name}")

        db.commit()

        # Backfill sap_item_code_id for any items already in DB.
        items_missing = db.query(MountingCleatItem).filter(
            MountingCleatItem.sap_code.isnot(None),
            MountingCleatItem.sap_item_code_id.is_(None),
        ).all()
        linked = 0
        for it in items_missing:
            sap_id = sap_map.get(it.sap_code.strip()) if it.sap_code else None
            if sap_id:
                it.sap_item_code_id = sap_id
                linked += 1
        if linked:
            db.commit()
            print(f"Linked {linked} MountingCleatItem rows to SAP item codes")

    finally:
        db.close()


def _bootstrap_sap_item_codes():
    """Seed sap_item_codes from FORMULAS 2018.xls 'SAP ITEM CODES' sheet (5 147 rows).
    Then backfill SkinFormulaIngredient.sap_item_code_id by matching sap_code → item_code.
    Idempotent — skips rows that already exist; re-runs the backfill on every startup."""
    import os, xlrd

    EXCEL_PATH = os.path.join(
        os.path.dirname(__file__), "..", "..", "Burt Costing Model", "FORMULAS 2018.xls"
    )
    if not os.path.exists(EXCEL_PATH):
        print(f"SAP bootstrap: Excel not found at {EXCEL_PATH} — skipping")
        return

    wb = xlrd.open_workbook(EXCEL_PATH)
    ws = wb.sheet_by_name("SAP ITEM CODES")

    db = SessionLocal()
    try:
        existing = {r.item_code for r in db.query(SapItemCode.item_code).all()}
        new_rows = []
        for row_idx in range(1, ws.nrows):
            code = str(ws.cell_value(row_idx, 0)).strip()
            if not code or code in existing:
                continue
            price = float(ws.cell_value(row_idx, 1) or 0)
            new_rows.append(SapItemCode(item_code=code, last_purch_price=price, is_active=True))

        if new_rows:
            db.bulk_save_objects(new_rows)
            db.commit()
            print(f"Seeded {len(new_rows)} SAP item codes")

        # Backfill sap_item_code_id on SkinFormulaIngredient rows that have a sap_code set
        sap_map = {r.item_code: r.id for r in db.query(SapItemCode).all()}
        ingredients = db.query(SkinFormulaIngredient).filter(
            SkinFormulaIngredient.sap_code.isnot(None)
        ).all()
        linked = 0
        for ing in ingredients:
            if ing.sap_code and not ing.sap_item_code_id:
                sap_id = sap_map.get(ing.sap_code.strip())
                if sap_id:
                    ing.sap_item_code_id = sap_id
                    linked += 1
        if linked:
            db.commit()
            print(f"Linked {linked} SkinFormulaIngredient rows to SAP item codes")

    finally:
        db.close()
