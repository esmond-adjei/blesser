import { Server } from "lucide-react"

export function ProviderIcon({ provider, className = "size-5" }: { provider: string; className?: string }) {
  if (["openai", "anthropic", "gemini", "ollama"].includes(provider)) return <img src={`/providers/${provider}.svg`} alt="" aria-hidden className={`${className} dark:invert`} />
  return <Server aria-hidden className={className} />
}
