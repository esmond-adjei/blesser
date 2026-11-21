import * as React from "react"

export interface ShellHeader {
  title: string
  actions?: React.ReactNode
}

export const ShellHeaderContext = React.createContext<(header: ShellHeader | null) => void>(() => {})

/** Puts a page's title and actions in the app's top bar instead of a second header. */
export function useShellHeader(header: ShellHeader | null) {
  const set = React.useContext(ShellHeaderContext)
  React.useEffect(() => {
    set(header)
  }, [set, header])
  React.useEffect(() => () => set(null), [set])
}
