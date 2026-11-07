import * as React from "react"
import { useNavigate } from "react-router-dom"
import * as api from "./api"
import { toastError } from "./toast"

/** Open the latest base CV's variant for a candidate, saved or not: the
 * editor resolves ?for= and nothing is created until "Save variant". With
 * no CV yet, the Documents page asks for one first. */
export function useTailorCv(candidateId: string) {
  const navigate = useNavigate()
  const [tailoring, setTailoring] = React.useState(false)
  const tailorCv = React.useCallback(async () => {
    setTailoring(true)
    try {
      const docs = await api.listCvs()
      const target = encodeURIComponent(candidateId)
      navigate(docs.length === 0 ? `/documents?for=${target}` : `/documents/${docs[0].id}?for=${target}`)
    } catch (err) {
      toastError(err, "Couldn't open your CV")
    } finally {
      setTailoring(false)
    }
  }, [candidateId, navigate])
  return { tailoring, tailorCv }
}
