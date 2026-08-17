/** WO v4.34.1 §3.5 — Customers admin (custom dispatch-map screen). Master-detail over the ~2160
 * customers: a debounced server-side search (GET /api/customers?q=&limit=50, the §3.2 filter) on the
 * left; on the right the selected customer's detail + an is_dealer flag toggle + the Contacts panel
 * (multi-contact CRUD with set-primary and soft-delete — the §0.6 reality). Admin-only (the module
 * already gates on isAdmin). */
import { useCallback, useEffect, useState } from 'react'
import { Search, Star, Pencil, Trash2, Plus, Check, X, Building2 } from 'lucide-react'

import { apiGet, apiPost, apiPut, apiDelete, handleApiError } from '../../lib/api'
import { useToast } from '../../components/ui/toast'
import { Card } from '../../components/ui/primitives'
import { Spinner, EmptyState } from '../../components/ui/feedback'

interface Customer {
  id: number; bp_code: string; name: string; email: string; telephone: string
  is_active: boolean; is_dealer: boolean
}
interface Contact {
  id: number; customer_id: number; name: string; role: string; email: string
  telephone: string; is_primary: boolean; is_active: boolean
}
/** WO v1.47 lane B — the END USER: ICB's customer is often a reseller or middleman and the
 *  body is actually FOR someone else. One row = the end-user COMPANY plus its contact PERSON. */
interface EndUser {
  id: number; customer_id: number; company_name: string; contact_name: string
  contact_role: string; contact_email: string; contact_telephone: string
  notes: string; is_primary: boolean; active: boolean
}

export function CustomersAdmin() {
  const toast = useToast()
  const [q, setQ] = useState('')
  const [list, setList] = useState<Customer[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const search = useCallback((term: string) => {
    setLoading(true)
    const qs = `limit=50${term.trim() ? `&q=${encodeURIComponent(term.trim())}` : ''}`
    apiGet<Customer[]>(`/api/customers?${qs}`)
      .then(setList)
      .catch((e) => handleApiError(e, toast.push))
      .finally(() => setLoading(false))
  }, [toast])

  useEffect(() => {
    const t = setTimeout(() => search(q), 250)         // debounce the 2160-row search
    return () => clearTimeout(t)
  }, [q, search])

  const selected = list.find((c) => c.id === selectedId) ?? null
  const patchInList = (c: Customer) => setList((prev) => prev.map((x) => (x.id === c.id ? c : x)))

  return (
    <div data-testid="admin-customers">
      <h1 className="mb-3 flex items-center gap-2 text-lg font-bold text-body">
        <Building2 size={20} /> Customers <span className="text-sm font-normal text-muted">(search the full list)</span>
      </h1>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[340px_1fr]">
        <div>
          <div className="mb-2 flex items-center gap-2 rounded-md border border-line bg-white px-3 py-2">
            <Search size={16} className="text-muted" />
            <input data-testid="customers-search" value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="Search name or BP code…" className="flex-1 text-sm outline-none" />
            {q && <button onClick={() => setQ('')} className="text-xs text-muted hover:text-body">clear</button>}
          </div>
          <Card className="p-0">
            {loading ? (
              <div className="flex justify-center p-6"><Spinner size={20} /></div>
            ) : list.length === 0 ? (
              <div className="p-4 text-center text-sm text-muted">No customers match.</div>
            ) : (
              <ul className="max-h-[70vh] divide-y divide-line overflow-y-auto">
                {list.map((c) => (
                  <li key={c.id}>
                    <button data-testid="customer-row" data-id={c.id} onClick={() => setSelectedId(c.id)}
                            className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-primary-light/40 ${selectedId === c.id ? 'bg-primary-light/60' : ''}`}>
                      <span className="min-w-0 truncate">
                        <span className="font-medium text-body">{c.name}</span>
                        {c.bp_code && <span className="ml-1.5 font-mono text-[11px] text-muted">{c.bp_code}</span>}
                      </span>
                      {c.is_dealer && (
                        <span className="shrink-0 rounded-full bg-primary-light/60 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-primary">dealer</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {!loading && list.length >= 50 && (
            <p className="mt-1 px-1 text-[11px] text-muted">Showing first 50 — refine the search to narrow.</p>
          )}
        </div>

        <div data-testid="customer-detail">
          {selected
            ? <CustomerDetail customer={selected} onUpdated={patchInList} />
            : <EmptyState title="Select a customer" hint="Search and pick a customer to view details and manage contacts." />}
        </div>
      </div>
    </div>
  )
}

function CustomerDetail({ customer, onUpdated }: { customer: Customer; onUpdated: (c: Customer) => void }) {
  const toast = useToast()
  const [savingDealer, setSavingDealer] = useState(false)

  async function toggleDealer() {
    setSavingDealer(true)
    try {
      const updated = await apiPut<Customer>(`/api/customers/${customer.id}`, { is_dealer: !customer.is_dealer })
      onUpdated(updated)
      toast.push({ kind: 'ok', message: updated.is_dealer ? 'Flagged as dealer.' : 'Dealer flag removed.' })
    } catch (e) {
      handleApiError(e, toast.push)
    } finally {
      setSavingDealer(false)
    }
  }

  return (
    <Card className="p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-lg font-bold text-body">{customer.name}</div>
          {customer.bp_code && <div className="font-mono text-xs text-muted">{customer.bp_code}</div>}
        </div>
        <label className="flex cursor-pointer items-center gap-2 rounded-md border border-line px-3 py-1.5 text-sm">
          <input data-testid="customer-is-dealer-toggle" type="checkbox" checked={customer.is_dealer}
                 disabled={savingDealer} onChange={toggleDealer} />
          <span className="font-semibold text-body">Dealer (chassis supplier)</span>
          {savingDealer && <Spinner size={12} />}
        </label>
      </div>
      <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
        <div><div className="text-[11px] uppercase tracking-wide text-muted">Email (legacy cache)</div><div className="text-body">{customer.email || '—'}</div></div>
        <div><div className="text-[11px] uppercase tracking-wide text-muted">Telephone (legacy cache)</div><div className="text-body">{customer.telephone || '—'}</div></div>
      </div>

      <ContactsPanel customerId={customer.id} />
      <div className="mt-5 border-t border-line pt-4">
        <EndUsersPanel customerId={customer.id} />
      </div>
    </Card>
  )
}

const EMPTY_CONTACT = { name: '', role: '', email: '', telephone: '' }

function ContactsPanel({ customerId }: { customerId: number }) {
  const toast = useToast()
  const [contacts, setContacts] = useState<Contact[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState(EMPTY_CONTACT)
  const [adding, setAdding] = useState(false)
  const [addDraft, setAddDraft] = useState({ ...EMPTY_CONTACT, is_primary: false })
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    apiGet<Contact[]>(`/api/customers/${customerId}/contacts`)
      .then(setContacts)
      .catch((e) => handleApiError(e, toast.push))
      .finally(() => setLoading(false))
  }, [customerId, toast])

  useEffect(() => { setEditingId(null); setAdding(false); load() }, [load])

  async function addContact() {
    if (!addDraft.name.trim() && !addDraft.email.trim() && !addDraft.telephone.trim()) {
      toast.push({ kind: 'error', message: 'Enter at least a name, email, or telephone.' }); return
    }
    setBusy(true)
    try {
      await apiPost(`/api/customers/${customerId}/contacts`, addDraft)
      toast.push({ kind: 'ok', message: 'Contact added.' })
      setAdding(false); setAddDraft({ ...EMPTY_CONTACT, is_primary: false }); load()
    } catch (e) { handleApiError(e, toast.push) } finally { setBusy(false) }
  }

  async function saveEdit(id: number) {
    setBusy(true)
    try {
      await apiPut(`/api/customers/${customerId}/contacts/${id}`, draft)
      toast.push({ kind: 'ok', message: 'Contact updated.' })
      setEditingId(null); load()
    } catch (e) { handleApiError(e, toast.push) } finally { setBusy(false) }
  }

  async function setPrimary(id: number) {
    setBusy(true)
    try {
      await apiPost(`/api/customers/${customerId}/contacts/${id}/set-primary`, {})
      load()
    } catch (e) { handleApiError(e, toast.push) } finally { setBusy(false) }
  }

  async function remove(id: number) {
    setBusy(true)
    try {
      await apiDelete(`/api/customers/${customerId}/contacts/${id}`)
      toast.push({ kind: 'ok', message: 'Contact removed.' })
      load()
    } catch (e) { handleApiError(e, toast.push) } finally { setBusy(false) }
  }

  return (
    <div data-testid="contacts-panel">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Contacts</h2>
        {!adding && (
          <button data-testid="contact-add" onClick={() => setAdding(true)}
                  className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1.5 text-xs font-semibold text-white hover:opacity-90">
            <Plus size={13} /> Add contact
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center p-4"><Spinner size={18} /></div>
      ) : (
        <div className="overflow-hidden rounded-md border border-line">
          <table className="w-full text-sm">
            <thead className="bg-surface-alt text-left text-xs text-muted">
              <tr>
                <th className="px-2 py-1.5 font-semibold">Primary</th>
                <th className="px-2 py-1.5 font-semibold">Name</th>
                <th className="px-2 py-1.5 font-semibold">Role</th>
                <th className="px-2 py-1.5 font-semibold">Email</th>
                <th className="px-2 py-1.5 font-semibold">Telephone</th>
                <th className="px-2 py-1.5 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {contacts.length === 0 && !adding && (
                <tr><td colSpan={6} className="px-2 py-3 text-center text-muted">No contacts yet.</td></tr>
              )}
              {contacts.map((c) => editingId === c.id ? (
                <tr key={c.id} data-testid="contact-row" data-id={c.id} className="border-t border-line bg-primary-light/20">
                  <td className="px-2 py-1.5">{c.is_primary && <Star size={14} className="fill-primary text-primary" />}</td>
                  <td className="px-2 py-1.5"><input value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} className="w-full rounded border border-line px-1.5 py-1 text-sm" /></td>
                  <td className="px-2 py-1.5"><input value={draft.role} onChange={(e) => setDraft((d) => ({ ...d, role: e.target.value }))} className="w-full rounded border border-line px-1.5 py-1 text-sm" /></td>
                  <td className="px-2 py-1.5"><input value={draft.email} onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))} className="w-full rounded border border-line px-1.5 py-1 text-sm" /></td>
                  <td className="px-2 py-1.5"><input value={draft.telephone} onChange={(e) => setDraft((d) => ({ ...d, telephone: e.target.value }))} className="w-full rounded border border-line px-1.5 py-1 text-sm" /></td>
                  <td className="px-2 py-1.5">
                    <div className="flex justify-end gap-1">
                      <button data-testid="contact-edit-save" onClick={() => saveEdit(c.id)} disabled={busy} title="Save"
                              className="rounded p-1 text-status-green hover:bg-status-green/10"><Check size={15} /></button>
                      <button onClick={() => setEditingId(null)} title="Cancel" className="rounded p-1 text-muted hover:bg-surface-alt"><X size={15} /></button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={c.id} data-testid="contact-row" data-id={c.id} className="border-t border-line">
                  <td className="px-2 py-1.5">
                    {c.is_primary
                      ? <span data-testid="contact-primary-star" title="Primary contact"><Star size={14} className="fill-primary text-primary" /></span>
                      : <button data-testid="contact-set-primary" onClick={() => setPrimary(c.id)} disabled={busy} title="Make primary"
                                className="text-muted hover:text-primary"><Star size={14} /></button>}
                  </td>
                  <td className="px-2 py-1.5 text-body">{c.name || <span className="text-muted">—</span>}</td>
                  <td className="px-2 py-1.5 text-body">{c.role || <span className="text-muted">—</span>}</td>
                  <td className="px-2 py-1.5 text-body">{c.email || <span className="text-muted">—</span>}</td>
                  <td className="px-2 py-1.5 text-body">{c.telephone || <span className="text-muted">—</span>}</td>
                  <td className="px-2 py-1.5">
                    <div className="flex justify-end gap-1">
                      <button data-testid="contact-edit" onClick={() => { setEditingId(c.id); setDraft({ name: c.name, role: c.role, email: c.email, telephone: c.telephone }) }}
                              title="Edit" className="rounded p-1 text-muted hover:bg-surface-alt hover:text-body"><Pencil size={14} /></button>
                      <button data-testid="contact-delete" onClick={() => remove(c.id)} disabled={busy}
                              title="Remove" className="rounded p-1 text-status-red hover:bg-status-red/10"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {adding && (
                <tr data-testid="contact-add-row" className="border-t border-line bg-primary-light/20">
                  <td className="px-2 py-1.5">
                    <input data-testid="contact-add-primary" type="checkbox" checked={addDraft.is_primary}
                           onChange={(e) => setAddDraft((d) => ({ ...d, is_primary: e.target.checked }))} title="Make primary" />
                  </td>
                  <td className="px-2 py-1.5"><input data-testid="contact-add-name" value={addDraft.name} placeholder="Name" onChange={(e) => setAddDraft((d) => ({ ...d, name: e.target.value }))} className="w-full rounded border border-line px-1.5 py-1 text-sm" /></td>
                  <td className="px-2 py-1.5"><input data-testid="contact-add-role" value={addDraft.role} placeholder="Role" onChange={(e) => setAddDraft((d) => ({ ...d, role: e.target.value }))} className="w-full rounded border border-line px-1.5 py-1 text-sm" /></td>
                  <td className="px-2 py-1.5"><input data-testid="contact-add-email" value={addDraft.email} placeholder="Email" onChange={(e) => setAddDraft((d) => ({ ...d, email: e.target.value }))} className="w-full rounded border border-line px-1.5 py-1 text-sm" /></td>
                  <td className="px-2 py-1.5"><input data-testid="contact-add-telephone" value={addDraft.telephone} placeholder="Telephone" onChange={(e) => setAddDraft((d) => ({ ...d, telephone: e.target.value }))} className="w-full rounded border border-line px-1.5 py-1 text-sm" /></td>
                  <td className="px-2 py-1.5">
                    <div className="flex justify-end gap-1">
                      <button data-testid="contact-add-save" onClick={addContact} disabled={busy} title="Save"
                              className="rounded p-1 text-status-green hover:bg-status-green/10"><Check size={15} /></button>
                      <button onClick={() => { setAdding(false); setAddDraft({ ...EMPTY_CONTACT, is_primary: false }) }} title="Cancel" className="rounded p-1 text-muted hover:bg-surface-alt"><X size={15} /></button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-1.5 text-[11px] text-muted">One primary contact per customer (enforced in the database). Removing a contact is a soft-delete — history is preserved.</p>
    </div>
  )
}

const EMPTY_END_USER = {
  company_name: '', contact_name: '', contact_role: '', contact_email: '', contact_telephone: '',
}

/** WO v1.47 lane B §3.3 — the end-user book, managed on the SAME screen as contacts (Default 4:
 *  a second section, not a new admin page). Deliberately the ContactsPanel shape: same table,
 *  same set-primary star, same soft-delete, same inline add row. */
function EndUsersPanel({ customerId }: { customerId: number }) {
  const toast = useToast()
  const [endUsers, setEndUsers] = useState<EndUser[]>([])
  const [loading, setLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState(EMPTY_END_USER)
  const [adding, setAdding] = useState(false)
  const [addDraft, setAddDraft] = useState({ ...EMPTY_END_USER, is_primary: false })
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    apiGet<EndUser[]>(`/api/customers/${customerId}/end-users`)
      .then(setEndUsers)
      .catch((e) => handleApiError(e, toast.push))
      .finally(() => setLoading(false))
  }, [customerId, toast])

  useEffect(() => { setEditingId(null); setAdding(false); load() }, [load])

  async function addEndUser() {
    if (!addDraft.company_name.trim()) {
      toast.push({ kind: 'error', message: 'End-user company name is required.' }); return
    }
    setBusy(true)
    try {
      await apiPost(`/api/customers/${customerId}/end-users`, addDraft)
      toast.push({ kind: 'ok', message: 'End user added.' })
      setAdding(false); setAddDraft({ ...EMPTY_END_USER, is_primary: false }); load()
    } catch (e) { handleApiError(e, toast.push) } finally { setBusy(false) }
  }

  async function saveEdit(id: number) {
    setBusy(true)
    try {
      await apiPut(`/api/customers/${customerId}/end-users/${id}`, draft)
      toast.push({ kind: 'ok', message: 'End user updated.' })
      setEditingId(null); load()
    } catch (e) { handleApiError(e, toast.push) } finally { setBusy(false) }
  }

  async function setPrimary(id: number) {
    setBusy(true)
    try {
      await apiPost(`/api/customers/${customerId}/end-users/${id}/set-primary`, {})
      load()
    } catch (e) { handleApiError(e, toast.push) } finally { setBusy(false) }
  }

  async function remove(id: number) {
    setBusy(true)
    try {
      await apiDelete(`/api/customers/${customerId}/end-users/${id}`)
      toast.push({ kind: 'ok', message: 'End user removed.' })
      load()
    } catch (e) { handleApiError(e, toast.push) } finally { setBusy(false) }
  }

  const field = (key: keyof typeof EMPTY_END_USER, placeholder: string, testid?: string) => (
    <input data-testid={testid} value={draft[key]} placeholder={placeholder}
           onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
           className="w-full rounded border border-line px-1.5 py-1 text-sm" />
  )
  const addField = (key: keyof typeof EMPTY_END_USER, placeholder: string, testid: string) => (
    <input data-testid={testid} value={addDraft[key]} placeholder={placeholder}
           onChange={(e) => setAddDraft((d) => ({ ...d, [key]: e.target.value }))}
           className="w-full rounded border border-line px-1.5 py-1 text-sm" />
  )

  return (
    <div data-testid="end-users-panel">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">End users</h2>
        {!adding && (
          <button data-testid="end-user-add" onClick={() => setAdding(true)}
                  className="flex items-center gap-1 rounded-md bg-primary px-2.5 py-1.5 text-xs font-semibold text-white hover:opacity-90">
            <Plus size={13} /> Add end user
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center p-4"><Spinner size={18} /></div>
      ) : (
        <div className="overflow-hidden rounded-md border border-line">
          <table className="w-full text-sm">
            <thead className="bg-surface-alt text-left text-xs text-muted">
              <tr>
                <th className="px-2 py-1.5 font-semibold">Primary</th>
                <th className="px-2 py-1.5 font-semibold">End-user company</th>
                <th className="px-2 py-1.5 font-semibold">Contact</th>
                <th className="px-2 py-1.5 font-semibold">Role</th>
                <th className="px-2 py-1.5 font-semibold">Email</th>
                <th className="px-2 py-1.5 font-semibold">Telephone</th>
                <th className="px-2 py-1.5 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {endUsers.length === 0 && !adding && (
                <tr><td colSpan={7} className="px-2 py-3 text-center text-muted">No end users yet.</td></tr>
              )}
              {endUsers.map((e) => editingId === e.id ? (
                <tr key={e.id} data-testid="end-user-row" data-id={e.id} className="border-t border-line bg-primary-light/20">
                  <td className="px-2 py-1.5">{e.is_primary && <Star size={14} className="fill-primary text-primary" />}</td>
                  <td className="px-2 py-1.5">{field('company_name', 'Company', 'end-user-edit-company')}</td>
                  <td className="px-2 py-1.5">{field('contact_name', 'Contact')}</td>
                  <td className="px-2 py-1.5">{field('contact_role', 'Role')}</td>
                  <td className="px-2 py-1.5">{field('contact_email', 'Email')}</td>
                  <td className="px-2 py-1.5">{field('contact_telephone', 'Telephone')}</td>
                  <td className="px-2 py-1.5">
                    <div className="flex justify-end gap-1">
                      <button data-testid="end-user-edit-save" onClick={() => saveEdit(e.id)} disabled={busy} title="Save"
                              className="rounded p-1 text-status-green hover:bg-status-green/10"><Check size={15} /></button>
                      <button onClick={() => setEditingId(null)} title="Cancel" className="rounded p-1 text-muted hover:bg-surface-alt"><X size={15} /></button>
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={e.id} data-testid="end-user-row" data-id={e.id} className="border-t border-line">
                  <td className="px-2 py-1.5">
                    {e.is_primary
                      ? <span data-testid="end-user-primary-star" title="Primary end user"><Star size={14} className="fill-primary text-primary" /></span>
                      : <button data-testid="end-user-set-primary" onClick={() => setPrimary(e.id)} disabled={busy} title="Make primary"
                                className="text-muted hover:text-primary"><Star size={14} /></button>}
                  </td>
                  <td className="px-2 py-1.5 font-medium text-body">{e.company_name}</td>
                  <td className="px-2 py-1.5 text-body">{e.contact_name || <span className="text-muted">—</span>}</td>
                  <td className="px-2 py-1.5 text-body">{e.contact_role || <span className="text-muted">—</span>}</td>
                  <td className="px-2 py-1.5 text-body">{e.contact_email || <span className="text-muted">—</span>}</td>
                  <td className="px-2 py-1.5 text-body">{e.contact_telephone || <span className="text-muted">—</span>}</td>
                  <td className="px-2 py-1.5">
                    <div className="flex justify-end gap-1">
                      <button data-testid="end-user-edit"
                              onClick={() => { setEditingId(e.id); setDraft({ company_name: e.company_name, contact_name: e.contact_name, contact_role: e.contact_role, contact_email: e.contact_email, contact_telephone: e.contact_telephone }) }}
                              title="Edit" className="rounded p-1 text-muted hover:bg-surface-alt hover:text-body"><Pencil size={14} /></button>
                      <button data-testid="end-user-delete" onClick={() => remove(e.id)} disabled={busy}
                              title="Remove" className="rounded p-1 text-status-red hover:bg-status-red/10"><Trash2 size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {adding && (
                <tr data-testid="end-user-add-row" className="border-t border-line bg-primary-light/20">
                  <td className="px-2 py-1.5">
                    <input data-testid="end-user-add-primary" type="checkbox" checked={addDraft.is_primary}
                           onChange={(e) => setAddDraft((d) => ({ ...d, is_primary: e.target.checked }))} title="Make primary" />
                  </td>
                  <td className="px-2 py-1.5">{addField('company_name', 'Company *', 'end-user-add-company')}</td>
                  <td className="px-2 py-1.5">{addField('contact_name', 'Contact', 'end-user-add-name')}</td>
                  <td className="px-2 py-1.5">{addField('contact_role', 'Role', 'end-user-add-role')}</td>
                  <td className="px-2 py-1.5">{addField('contact_email', 'Email', 'end-user-add-email')}</td>
                  <td className="px-2 py-1.5">{addField('contact_telephone', 'Telephone', 'end-user-add-telephone')}</td>
                  <td className="px-2 py-1.5">
                    <div className="flex justify-end gap-1">
                      <button data-testid="end-user-add-save" onClick={addEndUser} disabled={busy} title="Save"
                              className="rounded p-1 text-status-green hover:bg-status-green/10"><Check size={15} /></button>
                      <button onClick={() => { setAdding(false); setAddDraft({ ...EMPTY_END_USER, is_primary: false }) }} title="Cancel" className="rounded p-1 text-muted hover:bg-surface-alt"><X size={15} /></button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-1.5 text-[11px] text-muted">The end user is the customer&apos;s customer — who the body is actually for. One primary per customer (enforced in the database); removing is a soft-delete, and costings already quoted keep the end user they were saved with.</p>
    </div>
  )
}
