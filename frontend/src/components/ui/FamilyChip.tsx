// RT3 — a body's FAMILY chip: a dot in the family colour + the family name (the name always travels with the
// colour). The family is data from the server (backend services/body_family.py: `trailer_family` on every
// /api/calculations row): the stored colour for the dot and the family's `ink` for the text (the light MES
// skin's ink, >= 4.6:1). This component holds no colour of its own.

export interface BodyFamily {
  id: number | null
  name: string
  colour: string
  ink: string
  sort_order: number
}

export function FamilyChip({ family, testId = 'family-chip' }: { family?: BodyFamily | null; testId?: string }) {
  if (!family) return null
  return (
    <span
      data-testid={testId}
      data-family={family.name}
      title={`Family: ${family.name}`}
      className="ml-1.5 inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-slate-200 bg-white px-1.5 align-middle text-[10.5px] font-bold leading-[1.5] tracking-[.02em]"
      style={{ color: family.ink }}
    >
      <span aria-hidden className="h-2 w-2 shrink-0 rounded-full" style={{ background: family.colour }} />
      {family.name}
    </span>
  )
}
