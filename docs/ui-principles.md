# UI principles

Why the CORBELscore window looks and behaves the way it does. Change the UI with these in mind.

## Two tabs, one question each

- **Control**: "what am I doing to the game?" Running it, and arranging how you run it.
- **View**: "what is going out?" Designing graphics and watching them live.

Everything the operator touches during a game is in Control. Everything a designer touches before a game is in Edit mode or in View → Graphics. F1 and F2 switch tabs.

## Edit and Locked are modes, so they must look different

Modes cause errors when people don't notice which one they are in (NN/g, *Modes in User Interfaces*). CORBELscore needs the modes anyway: a scoring control that also moves when dragged would be a disaster on air. So:

- Edit mode has **two strong signals**: an amber EDITING band across the window and a dotted grid behind the controls. Locked has neither.
- In Edit mode, controls **do not fire**. Shortcuts still do, so a game in progress is never stuck.
- The switch is one click, always in the same place (top right), with E and L as keys.
- Undo covers layout and design changes, and **never** rewinds a score or a clock. Those are separate histories, because the game keeps running while you tidy the layout.

## Direct manipulation, with a keyboard way too

Drag a field from the Library onto the page; drag a control to move it; drag an edge or corner to resize (NN/g, *Direct Manipulation*).

- Feedback is immediate: a ghost shows where the control will land, and others move aside as you drag (NN/g, *Response Times: the 3 important limits*: under 0.1 s feels instant).
- Every drag has a keyboard equivalent: arrows move, Shift + arrows resize, Delete removes.
- Nothing overlaps: the grid pushes controls down instead of stacking them.

## Pages, like a button deck

Controls live on pages (Game, Teams, …), the model operators already know from Stream Deck and Bitfocus Companion. Setup fields (team names, colours, logos) start on their own page so the game page holds only what changes during play. A shortcut does not need a place on any page: its key always works.

## Sized for game pressure

- Targets are well above WCAG 2.2's 24 × 24 px minimum (2.5.8): score steps are at least 38 px tall, Start/Stop is 46 px and spans its control, and the smallest buttons anywhere are 30 px.
- In Locked mode the rows stretch to fit the page to the window (30 to 60 px per row), so a page fits without scrolling unless it is very tall.
- Controls adapt to their own size with CSS container queries: a wide counter puts its value beside its steps, a short clock drops its fine adjustments, a narrow button shrinks its label.
- Values use tabular figures, so digits don't jump as clocks run.

## Status is a colour and a word

Every state shows as both: RUNNING, STOPPED, LIVE, OVERRIDE, WAITING, and the header lights LIVE / FILES / WEB with a tooltip that explains the problem. Colour alone fails for colour-blind operators and on washed-out monitors.

## Don't make the user think

- One click does the whole job. Picture opens the file picker and the picture arrives at its own size; Board puts a board inside this one and adds its On air switch to the control page; Connect is the only thing that connects.
- Fewer, clearer choices. Align, distribute, order and duplicate live in one Arrange menu; view options in one Show menu.
- Defaults that are usually right: new text hugs its words; a field dropped on a board gets a fixed box; a blank project opens in Edit.
- The thing you are changing stays visible: split view keeps the controls under the board, and opacity previews while you drag.

## The design system

- Five named colours (Basalt, Limestone, Patina, Brass, Terracotta), everything else derived and contrast-checked, so the dark and light schemes stay consistent. See [design-system.md](design-system.md).
- Flat panels, hairline borders; shadows only on what floats.
- Red Hat Text to read, Red Hat Display for numbers and titles, tracked capitals for labels.
- Words on buttons, not icons alone.
- One accent colour for the main action on screen.

## Sources

- [Modes in User Interfaces: When They Help and When They Hurt Users](https://www.nngroup.com/articles/modes/), Nielsen Norman Group
- [Direct Manipulation: Definition](https://www.nngroup.com/articles/direct-manipulation/), Nielsen Norman Group
- [Response Times: The 3 Important Limits](https://www.nngroup.com/articles/response-times-3-important-limits/), Nielsen Norman Group
- [Understanding SC 2.5.8: Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), W3C
- [CSS container queries](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment/Container_queries), MDN
- [Bitfocus Companion](https://bitfocus.io/companion)
