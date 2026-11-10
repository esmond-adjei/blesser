const PAYMENT_AUTOCOMPLETE = /^(?:.*\s)?cc-/
const PAYMENT_WORDS =
  /card ?number|credit ?card|debit ?card|cvv|cvc|csc|security ?code|card ?expir|expiry ?date.*card|iban|swift ?code|\bbic\b|routing ?number|sort ?code|account ?number|bank ?account|pin ?code|\bpin\b/i
const SECRET_WORDS = /password|passcode|passwd|one[- ]time code|\botp\b|\b2fa\b|verification code/i

/** Security rule: password, secret and payment fields are never collected or filled. */
export function isForbidden(el: Element, label: string): boolean {
  const type = (el.getAttribute("type") ?? "").toLowerCase()
  if (type === "password") return true
  const autocomplete = (el.getAttribute("autocomplete") ?? "").toLowerCase()
  if (PAYMENT_AUTOCOMPLETE.test(autocomplete) || /(?:current|new)-password|one-time-code/.test(autocomplete)) return true
  const haystack = [el.getAttribute("name"), el.id, el.getAttribute("placeholder"), el.getAttribute("aria-label"), label].join(" ")
  return PAYMENT_WORDS.test(haystack) || SECRET_WORDS.test(haystack)
}
