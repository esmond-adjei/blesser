import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "../styles.css"
import { followTheme } from "../shared/ui"
import { Popup } from "./Popup"

followTheme()
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Popup />
  </StrictMode>,
)
