import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "../styles.css"
import { followTheme } from "../shared/ui"
import { Options } from "./Options"

followTheme()
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Options />
  </StrictMode>,
)
