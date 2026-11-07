import type { SchoolTier } from "../../lib/types"
import { sentence } from "../../lib/entities"
import { tierColors } from "../../lib/schools"

export function SchoolTierText({ tier }: { tier: SchoolTier }) {
  return <span className={tierColors[tier]}>{sentence(tier)} tier</span>
}
