import * as React from "react"

export type Track = <T>(work: Promise<T>) => Promise<T | undefined>

export const AutosaveContext = React.createContext<Track>(async (work) => work)

/** Wraps an autosave so the settings section reports "Saving…" then "Saved"; failures toast. */
export function useAutosave(): Track {
  return React.useContext(AutosaveContext)
}
