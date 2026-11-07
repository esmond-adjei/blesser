import { Link } from "react-router-dom"
import { useAllRunSchools } from "../../lib/queries"

export function ApplicationSchoolLink({ name }: { name: string }) {
  const { items } = useAllRunSchools()
  const key = name.trim().toLocaleLowerCase()
  const matches = key ? items.filter(({ school }) => school.name.trim().toLocaleLowerCase() === key) : []
  if (matches.length !== 1) return <>{name}</>
  return (
    <Link to={`/schools/${matches[0].school.id}`} className="pointer-events-auto relative z-10 hover:text-foreground hover:underline">
      {name}
    </Link>
  )
}
