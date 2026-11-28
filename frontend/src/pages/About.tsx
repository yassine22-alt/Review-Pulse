import { useEffect, useState } from "react";
import { api } from "../api";
import { Field } from "../ui";

export interface Details { occupancy: string; location: string; base_pack: string }
interface Pack { name: string; rules: number; docs: string[] }

const USES = ["Residential, one or two homes", "Residential, apartment building", "Office", "Retail", "School or childcare",
  "Health care", "Assembly", "Industrial", "Storage", "Mixed use"];

/** The building and the rule set of a submission. The use and the place are recorded and head the correction list; they
 *  choose no rule. The checks come from the uploaded document unless a rule set is added here. */
export function AboutFields({ value, onChange }: { value: Details; onChange: (v: Details) => void }) {
  const [packs, setPacks] = useState<Pack[]>([]);
  useEffect(() => { api<Pack[]>("/api/packs").then(setPacks).catch(() => setPacks([])); }, []);
  return (
    <>
      <Field label="Building use" hint="In your office's words. It is recorded; it does not choose rules.">
        <input list="building-uses" maxLength={160} value={value.occupancy}
          onChange={(e) => onChange({ ...value, occupancy: e.target.value })} />
      </Field>
      <datalist id="building-uses">{USES.map((u) => <option key={u} value={u} />)}</datalist>
      <Field label="Location" hint="Town, district or jurisdiction.">
        <input maxLength={160} value={value.location} onChange={(e) => onChange({ ...value, location: e.target.value })} />
      </Field>
      <Field label="Rule set added to your document">
        <select value={value.base_pack} onChange={(e) => onChange({ ...value, base_pack: e.target.value })}>
          <option value="">None, only your document</option>
          {packs.map((p) => (
            <option key={p.name} value={p.name}>{p.name}: {p.rules} example rules, not your local code</option>
          ))}
        </select>
      </Field>
    </>
  );
}
