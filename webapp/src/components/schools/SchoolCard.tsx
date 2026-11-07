import * as React from "react"
import { BookOpen, ExternalLink, Layers, Pencil, SquareArrowOutUpRight, Users } from "lucide-react"
import { useNavigate } from "react-router-dom"
import type { School } from "../../lib/types"
import { schoolFacultyCount, tierColors } from "../../lib/schools"
import { plural } from "../../lib/entities"
import { FactList } from "../entity/facts"
import { SchoolImage } from "../entity/SchoolImage"
import { MenuItem } from "../ui/menu"
import { RowMenu, type RowMenuVariant } from "../ui/row-menu"
import { CoverCard } from "../cards/CoverCard"
import { SchoolTierText } from "./SchoolTierText"
import { SchoolDialog } from "../dialogs/ProspectDialogs"

export function SchoolCard({
  school,
  onOpen,
  active = false,
}: {
  school: School
  onOpen: () => void
  active?: boolean
  preview?: boolean
}) {
  const faculty = schoolFacultyCount(school)
  return (
    <CoverCard label={`Open ${school.name}`} onOpen={onOpen} active={active} className="h-full">
      <div className="pointer-events-none relative g-ecard__media">
        <SchoolImage src={school.image_url} name={school.name} variant="card" className="h-full rounded-none" />
      </div>
      <h3 className="pointer-events-none relative g-ecard__title line-clamp-2">{school.name}</h3>
      <p className="pointer-events-none relative g-ecard__meta g-clamp-1">{school.country || "Country unknown"}</p>
      <div className="pointer-events-none relative">
        <FactList
          size="sm"
          facts={[
            { icon: BookOpen, value: plural(school.programs.length, "programme") },
            { icon: Users, value: `${faculty} faculty` },
            school.tier && { icon: Layers, iconClassName: tierColors[school.tier], value: <SchoolTierText tier={school.tier} /> },
          ]}
        />
      </div>
      <SchoolRowMenu school={school} />
    </CoverCard>
  )
}

export function SchoolRowMenu({ school, className, variant = "row" }: { school: School; className?: string; variant?: RowMenuVariant }) {
  const navigate = useNavigate()
  const [editing, setEditing] = React.useState(false)
  return (
    <>
    <RowMenu label={`Manage ${school.name}`} className={className} variant={variant}>
      {variant !== "header" && <MenuItem onSelect={() => navigate(`/schools/${school.id}`)}>
        <SquareArrowOutUpRight /> Open page
      </MenuItem>}
      <MenuItem onSelect={() => setEditing(true)}><Pencil /> Edit</MenuItem>
      {school.website_url && (
        <MenuItem onSelect={() => window.open(school.website_url ?? "", "_blank", "noopener,noreferrer")}>
          <ExternalLink /> Website
        </MenuItem>
      )}
    </RowMenu>
    {editing && <SchoolDialog existing={school} open onOpenChange={setEditing} />}
    </>
  )
}
