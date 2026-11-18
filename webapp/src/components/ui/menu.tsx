import * as React from "react"
import { ContextMenu as Ctx, DropdownMenu as Drop } from "radix-ui"
import { ChevronRight, MoreHorizontal } from "lucide-react"
import { Button, cn } from "@blesser/ui"

export type MenuAction =
  | { kind?: "item"; label: string; icon?: React.ReactNode; onSelect?: () => void; href?: string; danger?: boolean; disabled?: boolean }
  | { kind: "separator" }
  | { kind: "radio"; label: string; icon?: React.ReactNode; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void }

type Parts = typeof Ctx | typeof Drop

const CONTENT = "bl-pop z-50 min-w-52 rounded-md border border-separator bg-surface-raised p-1 text-ink shadow-elevation-2 outline-none"
const ITEM =
  "flex h-9 cursor-pointer items-center gap-2.5 rounded-sm px-2.5 text-callout outline-none select-none data-[highlighted]:bg-highlight data-[disabled]:cursor-default data-[disabled]:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-ink-secondary"

function Items({ P, actions }: { P: Parts; actions: MenuAction[] }) {
  return actions.map((a, i) => {
    if (a.kind === "separator") return <P.Separator key={i} className="mx-1 my-1 h-px bg-separator" />
    if (a.kind === "radio")
      return (
        <P.Sub key={i}>
          <P.SubTrigger className={cn(ITEM, "data-[state=open]:bg-highlight")}>
            {a.icon}
            <span className="flex-1">{a.label}</span>
            <ChevronRight className="text-ink-tertiary" />
          </P.SubTrigger>
          <P.Portal>
            <P.SubContent sideOffset={4} className={CONTENT}>
              <P.RadioGroup value={a.value} onValueChange={a.onChange}>
                {a.options.map((o) => (
                  <P.RadioItem key={o.value} value={o.value} className={cn(ITEM, "pl-8 relative")}>
                    <P.ItemIndicator className="absolute left-2.5 size-1.5 rounded-full bg-forest" />
                    {o.label}
                  </P.RadioItem>
                ))}
              </P.RadioGroup>
            </P.SubContent>
          </P.Portal>
        </P.Sub>
      )
    const body = (
      <>
        {a.icon}
        {a.label}
      </>
    )
    return (
      <P.Item
        key={i}
        disabled={a.disabled}
        onSelect={a.onSelect}
        asChild={!!a.href}
        className={cn(ITEM, a.danger && "text-critical [&_svg]:text-critical data-[highlighted]:bg-critical-soft")}
      >
        {a.href ? (
          <a href={a.href} target="_blank" rel="noopener noreferrer">
            {body}
          </a>
        ) : (
          body
        )}
      </P.Item>
    )
  })
}

/** Right-click (or long-press) menu for a row or card. */
export function ActionContextMenu({ actions, children }: { actions: MenuAction[]; children: React.ReactElement }) {
  return (
    <Ctx.Root>
      <Ctx.Trigger asChild>{children}</Ctx.Trigger>
      <Ctx.Portal>
        <Ctx.Content className={CONTENT} collisionPadding={8}>
          <Items P={Ctx} actions={actions} />
        </Ctx.Content>
      </Ctx.Portal>
    </Ctx.Root>
  )
}

/** The same menu behind a visible button, for touch and keyboard. */
export function ActionMenuButton({ actions, label, className }: { actions: MenuAction[]; label: string; className?: string }) {
  return (
    <Drop.Root>
      <Drop.Trigger asChild>
        <Button size="sm" variant="quiet" iconOnly aria-label={label} className={cn("text-ink-secondary", className)} icon={<MoreHorizontal />} />
      </Drop.Trigger>
      <Drop.Portal>
        <Drop.Content align="end" sideOffset={6} collisionPadding={8} className={CONTENT}>
          <Items P={Drop} actions={actions} />
        </Drop.Content>
      </Drop.Portal>
    </Drop.Root>
  )
}
