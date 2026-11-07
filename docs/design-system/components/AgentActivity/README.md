# AgentActivity

Agent activity is the work behind an answer: what the model thought and the tools it called, folded into one line once it has answered.

In the app: `AgentTrace`, `WorkGroup`, `ToolGroup`, `ToolRow` and `Thought` in `components/cards/AgentTrace.tsx`; Gradis replies use the grouped form, run tasks the ungrouped one.

Head (`.g-activity__head`): a 16px icon, a label and a chevron, in `callout` medium `label-tertiary`. While working, the icon spins and the label shimmers (`.g-shimmer`) and says what is happening in the present tense ("Reading 12 papers by Guanya Shi", "Thinking"). Once answered it folds and summarises ("Thought, 3 actions"), with "1 failed" in `critical` when a call failed. The group is open while the model works and folds when the answer starts, unless the reader has toggled it.

Body (`.g-activity__body`): indented 8px behind a 2px `separator` rule; the model's text between calls in `label-secondary`, thoughts faded, and tool calls in `.g-tools`: a `radius-xl` box of `.g-tool` rows (12px medium `label-tertiary` on `fill-quiet` at 40%, a 16px status icon: the tool's icon in `tint` when done, a spinner while running, a `critical` x when failed). A row expands to its parameters and result in `fill-quiet` wells.

Thoughts alone (`Thought`): "Thinking" or "Thoughts" with a brain icon; while live, the latest lines show under the head, fading in from the top.
