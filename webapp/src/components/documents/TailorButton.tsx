import { FileText } from "lucide-react"
import { useTailorCv } from "../../lib/tailorCv"
import { Button } from "../ui/button"

export function TailorButton({ candidateId }: { candidateId: string }) {
  const { tailoring, tailorCv } = useTailorCv(candidateId)
  return (
    <Button data-tooltip="Create or open a CV variant tailored to this professor" size="sm" variant="outline" disabled={tailoring} onClick={() => void tailorCv()}>
      <FileText /> {tailoring ? "Opening…" : "Tailor my CV"}
    </Button>
  )
}
