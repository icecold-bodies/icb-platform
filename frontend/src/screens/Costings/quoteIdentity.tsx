/**
 * How a costing's NUMBER is shown wherever a list names one (v1.51).
 *
 * A repair carries two identifiers and they are not interchangeable:
 *
 *   * the internal body-series record number ("L9976/08/2026"), minted for
 *     every costing so the MES has one key for the job, and
 *   * the customer-facing R-number ("R-2001"), issued once at the first
 *     Approve and printed on the quotation the customer actually receives.
 *
 * Through v1.50 the board showed only the first. Michael's report (25 Aug):
 * Lezette quotes R-2001 to a customer, searches the board for it, and finds
 * nothing — the number she is being asked about is on the detail page and
 * nowhere in the list. So the R-number is the PRIMARY value here and the
 * record number sits under it, still present because it is what the floor and
 * the job cards use.
 *
 * A helper rather than JSX pasted into one table: three separate surfaces
 * render a quote number for rows that can be repairs, and a repair whose
 * number is missing must degrade the same way in all of them.
 */
import type { Costing } from '../../data/costingsData'

/** The customer-facing number, or null when this row has none to show. */
export function customerQuoteNumber(c: Pick<Costing, 'repair_document_number'>): string | null {
  const n = (c.repair_document_number ?? '').trim()
  return n || null
}

/** Both numbers as one lowercase haystack, for a search box to test against. */
export function quoteSearchText(
  c: Pick<Costing, 'quote_number' | 'repair_document_number'>,
): string {
  return `${c.quote_number ?? ''} ${c.repair_document_number ?? ''}`.toLowerCase()
}

/**
 * The Quote # cell.
 *
 * A repair that has never been saved has no R-number yet — it is issued on the
 * first Approve — so it shows its record number ALONE rather than a blank line
 * with a subtitle under it. That is the only degraded state there is, and it is
 * the state every brand-new repair passes through.
 */
export function QuoteNumberCell({ c }: { c: Costing }) {
  const customer = customerQuoteNumber(c)
  if (!customer) {
    return <span data-testid="quote-number-primary">{c.quote_number}</span>
  }
  return (
    <span className="block leading-tight">
      <span data-testid="quote-number-primary" className="block">
        {customer}
      </span>
      <span
        data-testid="quote-number-internal"
        title="Internal costing number"
        className="block text-[10px] font-normal text-muted"
      >
        {c.quote_number}
      </span>
    </span>
  )
}
