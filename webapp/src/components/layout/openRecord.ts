import * as React from "react"
import { useNavigate } from "react-router-dom"
import { fullPageFor, type PreviewRef } from "../../lib/previewRoutes"
import { artifactPreview } from "../gradis/GradisArtifactPreview"
import { useDetailPanelOptional, useInDetailRail } from "./DetailPanel"

/** Opens in the detail panel, or the full page when the kind has no panel view or the screen no rail. */
export function useOpenRecord() {
  const panel = useDetailPanelOptional()
  const navigate = useNavigate()
  const inRail = useInDetailRail()
  const open = React.useCallback(
    (ref: PreviewRef, title: string) => {
      const preview = panel ? artifactPreview(ref) : null
      if (!panel || !preview) {
        const to = fullPageFor(ref)
        if (to) navigate(to)
        return
      }
      panel.setPanel(preview.node, { title, ref, actions: preview.actions, push: inRail })
    },
    [panel, navigate, inRail],
  )
  const shown = panel?.railVisible ? panel.previewRef : null
  const isOpen = (ref: Pick<PreviewRef, "kind" | "id">) => shown?.kind === ref.kind && shown.id === ref.id
  return { open, isOpen }
}
