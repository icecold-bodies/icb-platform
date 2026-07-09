/** Admin "Master Data" resource registry (WO v4.26 origin; v1.40.6 Master-Data overhaul).
 *
 * Every menu item carries:
 *  - `permKey`  — the STABLE identity (`admin.<key>`, mirrored verbatim in the backend
 *    PERMISSION_CATALOGUE) the BA boxes into roles/permissions. Never rename.
 *  - `displayId` — the short human tag on the sidebar badge (O1/S3/M2…). FROZEN once
 *    assigned: items sort alphabetically inside their group, but a badge never renumbers —
 *    future items keep alphabetical placement and take the group's next free number
 *    (ADR 0035). Reference items by displayId in conversation, by permKey in grants.
 *  - `icon` — lucide, rendered at 15px in the grouped sidebar.
 */
import type { LucideIcon } from 'lucide-react'
import {
  Activity, AlertTriangle, BadgeDollarSign, BookOpen, Building2, ClipboardCheck,
  FileSignature, Inbox, LayoutTemplate, Merge, Refrigerator, RotateCcw, SearchX,
  SlidersHorizontal, Timer, Truck, Workflow,
} from 'lucide-react'

import { apiGet } from '../../lib/api'

export type FieldType = 'text' | 'number' | 'bool' | 'textarea' | 'date' | 'time' | 'select'

export interface SelectOption { value: string; label: string }

export interface FieldDef {
  name: string
  label: string
  type?: FieldType
  required?: boolean
  default?: string | number | boolean
  validateFormula?: boolean   // formula_expression — live parse-check via the backend
  oitmAutocomplete?: boolean  // sap_code — typeahead from /api/admin/oitm-search
  // type 'select' — a static list, or an async loader (e.g. the chassis-type picture library).
  options?: SelectOption[] | (() => Promise<SelectOption[]>)
}

export interface ResourceConfig {
  key: string
  title: string
  basePath: string                          // e.g. /api/admin/bom-rules
  columns: { key: string; label: string }[] // table display columns
  fields: FieldDef[]                          // create/edit form fields
  custom?: boolean                            // WO v4.33 — rendered by a dedicated component, not AdminCrudTable
  icon: LucideIcon                            // v1.40.6 — sidebar icon
  displayId: string                           // v1.40.6 — frozen badge tag (O1/S3/M2…)
  permKey: `admin.${string}`                  // v1.40.6 — stable permission key (admin.<key>)
}

export const ADMIN_RESOURCES: Record<string, ResourceConfig> = {
  // WO v4.36b §3.3 — Health Check dashboard (custom screen; aggregates the visual-integrity flag streams).
  'health-check': {
    key: 'health-check',
    title: 'Health Check',
    basePath: '/api/visual-integrity/flags/summary',
    columns: [],
    fields: [],
    custom: true,
    icon: Activity, displayId: 'O3', permKey: 'admin.health-check',
  },
  // WO v4.36c §3.2 — Kenny's QC inspection inbox + form (custom screen; ?chassis= drives the form view).
  'qc': {
    key: 'qc',
    title: 'QC inspection',
    basePath: '/api/qc/awaiting',
    columns: [],
    fields: [],
    custom: true,
    icon: ClipboardCheck, displayId: 'O6', permKey: 'admin.qc',
  },
  // WO v4.38 — the feedback tickets inbox joins the module (was an orphan /admin/feedback route
  // linked from nowhere; the URL is unchanged — /admin/:resource now serves it).
  feedback: {
    key: 'feedback',
    title: 'Feedback inbox',
    basePath: '/api/admin/feedback',
    columns: [],
    fields: [],
    custom: true,
    icon: Inbox, displayId: 'O1', permKey: 'admin.feedback',
  },
  // WO v4.36c §3.3 — QC defect-categories DDM (flat CRUD; admin-editable taxonomy, §0.5). Backend
  // /api/admin/defect-categories shipped in §3.1; DELETE soft-deactivates (row persists is_active=false,
  // re-editable to reactivate — preserves the immutable qc_inspections audit, §3.0 §3d).
  'defect-categories': {
    key: 'defect-categories',
    title: 'QC defect categories',
    basePath: '/api/admin/defect-categories',
    columns: [
      { key: 'name', label: 'Category' }, { key: 'sort_order', label: 'Order' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      { name: 'name', label: 'Category name', required: true },
      { name: 'sort_order', label: 'Sort order', type: 'number', default: 100 },
      { name: 'is_active', label: 'Active', type: 'bool', default: true },
    ],
    icon: AlertTriangle, displayId: 'M4', permKey: 'admin.defect-categories',
  },
  'spec-options': {
    key: 'spec-options',
    title: 'Spec options (DDM dropdowns)',
    basePath: '/api/admin/bom-spec-options',
    columns: [
      { key: 'spec_field_type', label: 'Field' }, { key: 'body_type', label: 'Body' },
      { key: 'option_label', label: 'Label' }, { key: 'spec_value', label: 'Value' },
      { key: 'sap_code', label: 'SAP code' }, { key: 'active', label: 'Active' },
      { key: 'priority', label: 'Prio' },
    ],
    fields: [
      { name: 'spec_field_type', label: 'Spec field type', required: true },
      { name: 'body_type', label: 'Body type', default: '*' },
      { name: 'section', label: 'Section', default: 'Vacuum Materials' },
      { name: 'option_label', label: 'Option label', required: true },
      { name: 'spec_value', label: 'Spec value', required: true },
      { name: 'sap_code', label: 'SAP code', oitmAutocomplete: true },
      { name: 'is_default', label: 'Default', type: 'bool', default: false },
      { name: 'priority', label: 'Priority', type: 'number', default: 100 },
      { name: 'active', label: 'Active', type: 'bool', default: true },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
    icon: SlidersHorizontal, displayId: 'S6', permKey: 'admin.spec-options',
  },
  rules: {
    key: 'rules',
    title: 'BOM rules',
    basePath: '/api/admin/bom-rules',
    columns: [
      { key: 'body_type', label: 'Body' }, { key: 'section', label: 'Section' },
      { key: 'panel', label: 'Panel' }, { key: 'output_field', label: 'Output' },
      { key: 'formula_expression', label: 'Formula' }, { key: 'priority', label: 'Prio' },
    ],
    fields: [
      { name: 'body_type', label: 'Body type', required: true },
      { name: 'section', label: 'Section', default: 'Vacuum Materials' },
      { name: 'panel', label: 'Panel', required: true },
      { name: 'output_field', label: 'Output field', default: 'qty' },
      { name: 'formula_expression', label: 'Formula', type: 'textarea', required: true, validateFormula: true },
      { name: 'priority', label: 'Priority', type: 'number', default: 100 },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
    icon: Workflow, displayId: 'S1', permKey: 'admin.rules',
  },
  lookups: {
    key: 'lookups',
    title: 'Rule lookups (spec → SAP code)',
    basePath: '/api/admin/bom-rule-lookups',
    columns: [
      { key: 'body_type', label: 'Body' }, { key: 'section', label: 'Section' },
      { key: 'lookup_type', label: 'Type' }, { key: 'lookup_key', label: 'Key' },
      { key: 'lookup_value', label: 'Value' },
    ],
    fields: [
      { name: 'body_type', label: 'Body type', required: true },
      { name: 'section', label: 'Section', default: 'Vacuum Materials' },
      { name: 'lookup_type', label: 'Lookup type', default: 'spec_to_sap_code' },
      { name: 'lookup_key', label: 'Lookup key', required: true },
      { name: 'lookup_value', label: 'Lookup value (SAP code)', required: true, oitmAutocomplete: true },
      { name: 'notes', label: 'Notes', type: 'textarea' },
    ],
    icon: BookOpen, displayId: 'S5', permKey: 'admin.lookups',
  },
  'price-overrides': {
    key: 'price-overrides',
    title: 'Price overrides',
    basePath: '/api/admin/material-price-overrides',
    columns: [
      { key: 'sap_code', label: 'SAP code' }, { key: 'override_price', label: 'Override' },
      { key: 'valid_from', label: 'From' }, { key: 'valid_to', label: 'To' },
      { key: 'reason', label: 'Reason' },
    ],
    fields: [
      { name: 'sap_code', label: 'SAP code', required: true, oitmAutocomplete: true },
      { name: 'override_price', label: 'Override price', type: 'number', required: true },
      { name: 'valid_from', label: 'Valid from', type: 'date' },
      { name: 'valid_to', label: 'Valid to', type: 'date' },
      { name: 'reason', label: 'Reason', type: 'textarea' },
    ],
    icon: BadgeDollarSign, displayId: 'S4', permKey: 'admin.price-overrides',
  },
  // WO v4.33 §3.3 — Nadie's Pre-Job Card template library (nested section editor, so a
  // dedicated screen renders instead of the generic AdminCrudTable; see PrejobTemplatesAdmin).
  'prejob-templates': {
    key: 'prejob-templates',
    title: 'Pre-Job templates',
    basePath: '/api/admin/prejob-templates',
    columns: [],
    fields: [],
    custom: true,
    icon: LayoutTemplate, displayId: 'S3', permKey: 'admin.prejob-templates',
  },
  // WO v4.33 scope addition — fridge DDM (flat shape: the generic CRUD table fits).
  'fridge-units': {
    key: 'fridge-units',
    title: 'Fridge units',
    basePath: '/api/admin/fridge-units',
    columns: [
      { key: 'manufacturer', label: 'Manufacturer' }, { key: 'model', label: 'Model' },
      { key: 'display_name', label: 'Display name' }, { key: 'mounting_drawing', label: 'Drawing' },
      { key: 'cutout_width_mm', label: 'Cutout W (mm)' }, { key: 'cutout_height_mm', label: 'Cutout H (mm)' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      { name: 'manufacturer', label: 'Manufacturer', required: true },
      { name: 'model', label: 'Model' },
      { name: 'display_name', label: 'Display name (fills {{fridge_make}})', required: true },
      { name: 'mounting_drawing', label: 'Mounting drawing', default: 'A' },
      { name: 'cutout_width_mm', label: 'Cutout width (mm)', type: 'number' },
      { name: 'cutout_height_mm', label: 'Cutout height (mm)', type: 'number' },
      { name: 'is_active', label: 'Active', type: 'bool', default: true },
    ],
    icon: Refrigerator, displayId: 'M2', permKey: 'admin.fridge-units',
  },
  // Chassis-type DDM (seeded 0021; the CRUD its docstring promised for v4.35). Same style as
  // fridge-units. `image_file` = the type's default PICTURE (0033): assigning one here auto-links
  // it to every chassis of this type (a chassis's own manual pick stays as the override).
  'chassis-models': {
    key: 'chassis-models',
    title: 'Chassis types',
    basePath: '/api/admin/chassis-models',
    columns: [
      { key: 'make', label: 'Make' }, { key: 'model', label: 'Model' },
      { key: 'category', label: 'Category' }, { key: 'max_payload_kg', label: 'Payload (kg)' },
      { key: 'image_file', label: 'Picture' }, { key: 'sort_order', label: 'Order' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      { name: 'make', label: 'Make', required: true },
      { name: 'model', label: 'Model', required: true },
      { name: 'category', label: 'Category', type: 'select', options: [
        { value: 'truck', label: 'Truck' }, { value: 'bakkie', label: 'Bakkie' }, { value: 'trailer', label: 'Trailer' },
      ] },
      { name: 'max_payload_kg', label: 'Max payload (kg)', type: 'number' },
      { name: 'image_file', label: 'Picture (auto-links to every chassis of this type)', type: 'select',
        options: async () => (await apiGet<{ file: string; label: string }[]>('/api/chassis-records/type-images'))
          .map((i) => ({ value: i.file, label: i.label })) },
      { name: 'sort_order', label: 'Sort order', type: 'number', default: 100 },
      { name: 'is_active', label: 'Active (inactive = hidden from the dropdowns)', type: 'bool', default: true },
      { name: 'code', label: 'Code (leave blank to auto-generate from make/model)' },
    ],
    icon: Truck, displayId: 'M1', permKey: 'admin.chassis-models',
  },
  // v1.40.6 — production stage thresholds (flat CRUD): how long panels should spend in a
  // stage (vacuum=8h, press=4h seeds). workday_start = the time-of-day the stage clock
  // starts on a slot's scheduled day; the /plan V/P cards render elapsed-vs-threshold bars.
  'production-thresholds': {
    key: 'production-thresholds',
    title: 'Production stage thresholds',
    basePath: '/api/admin/production-thresholds',
    columns: [
      { key: 'stage_code', label: 'Stage code' }, { key: 'label', label: 'Label' },
      { key: 'threshold_hours', label: 'Threshold (h)' }, { key: 'workday_start', label: 'Clock starts' },
      { key: 'is_active', label: 'Active' },
    ],
    fields: [
      { name: 'stage_code', label: 'Stage code (stable key, e.g. vacuum)', required: true },
      { name: 'label', label: 'Label (shown on cards)', required: true },
      { name: 'threshold_hours', label: 'Threshold hours', type: 'number', required: true },
      { name: 'workday_start', label: 'Clock starts at (time of day)', type: 'time', default: '07:00' },
      { name: 'is_active', label: 'Active (inactive = no progress bars)', type: 'bool', default: true },
    ],
    icon: Timer, displayId: 'M3', permKey: 'admin.production-thresholds',
  },
  // v1.41.0 §9 P1 — admin-only Production Flow floor reset (journaled floor_reset event;
  // the FIRST admin.* key that is also enforced server-side by its endpoint).
  'floor-reset': {
    key: 'floor-reset',
    title: 'Floor reset (Production Flow)',
    basePath: '/api/plan/floor-reset',
    columns: [],
    fields: [],
    custom: true,
    icon: RotateCcw, displayId: 'M5', permKey: 'admin.floor-reset',
  },
  // WO v4.33.1 §3.1 — admin nav-aid: Pre-Job Cards awaiting sign-off (custom list view, not CRUD).
  'prejob-signoffs': {
    key: 'prejob-signoffs',
    title: 'Pre-Job sign-offs',
    basePath: '/api/prejob-cards/outstanding',
    columns: [],
    fields: [],
    custom: true,
    icon: FileSignature, displayId: 'O5', permKey: 'admin.prejob-signoffs',
  },
  // WO v4.34.1 §3.5 — Customers (searchable 2160-row list + detail + Contacts panel CRUD +
  // is_dealer flag). Custom screen: master-detail, not the flat AdminCrudTable.
  customers: {
    key: 'customers',
    title: 'Customers',
    basePath: '/api/customers',
    columns: [],
    fields: [],
    custom: true,
    icon: Building2, displayId: 'S2', permKey: 'admin.customers',
  },
  // WO v4.36a §3.6 — Find Orphan Chassis (custom read-only list; recovery actions added incrementally).
  'orphan-chassis': {
    key: 'orphan-chassis',
    title: 'Find Orphan Chassis',
    basePath: '/api/admin/chassis/orphans',
    columns: [],
    fields: [],
    custom: true,
    icon: SearchX, displayId: 'O2', permKey: 'admin.orphan-chassis',
  },
  // WO v4.36a §3.6 — Merge Chassis (custom: loser/winner pickers → preview → confirm merge).
  'merge-chassis': {
    key: 'merge-chassis',
    title: 'Merge Chassis',
    basePath: '/api/admin/chassis',
    columns: [],
    fields: [],
    custom: true,
    icon: Merge, displayId: 'O4', permKey: 'admin.merge-chassis',
  },
}

/** v1.40.6 — the grouped sidebar (Michael's WO): operations vs system-admin vs manufacturing
 * data, ALPHABETICAL by title inside each group. displayId badges are frozen (see header). */
export interface AdminGroup { id: 'ops' | 'system' | 'mfg'; label: string; items: string[] }

export const ADMIN_GROUPS: AdminGroup[] = [
  {
    id: 'ops', label: 'Monitor & operate',
    items: ['feedback', 'orphan-chassis', 'health-check', 'merge-chassis', 'prejob-signoffs', 'qc'],
  },
  {
    id: 'system', label: 'System administration',
    items: ['rules', 'customers', 'prejob-templates', 'price-overrides', 'lookups', 'spec-options'],
  },
  {
    id: 'mfg', label: 'Manufacturing data',
    items: ['chassis-models', 'floor-reset', 'fridge-units', 'production-thresholds', 'defect-categories'],
  },
]

export const ADMIN_ORDER = ADMIN_GROUPS.flatMap((g) => g.items)
