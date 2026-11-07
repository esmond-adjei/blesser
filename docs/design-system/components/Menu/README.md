# Menu

A menu lists actions on one thing (a run, a chat, a match, a draft), opened from a "More actions" button or a toolbar control.

In the app: `components/ui/menu.tsx` (`Menu`, `MenuItem`, `MenuSeparator`) and `ui/row-menu.tsx` (the hover trigger, see SidebarRow). The menu is portalled to the body, opens 4px below its trigger aligned to its end, flips up when short of room, and scrolls past 320px. Escape closes it and returns focus to the trigger.

Markup: `.g-menu` (`role="menu"`, `aria-label`) holding `.g-menu-item` buttons (`role="menuitem"`, a 16px icon, a verb-first label), `.g-menu-sep` between groups, and `.g-menu-item--destructive` (Delete) last.

Look: 224px wide, `surface-raised`, 1px `separator` border, `elevation-2`, `radius-lg` with a 4px inset so items are `radius-md`. Items are 14px text with 8px by 10px padding; hover fills `fill-quiet` (not `tint`). Destructive items stay `critical` on hover. Disabled items are at 50%. A selected option in a sort menu shows a 16px `tint` check at the end.

Busy labels end in an ellipsis while their action runs ("Pausing...").

Don't: put more than seven items in one menu, or hide the only way to do something in it.
