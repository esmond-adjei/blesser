export function saveFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Revoke after the click has been handled, not before.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
