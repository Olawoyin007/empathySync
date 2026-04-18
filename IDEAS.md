# Ideas Log

A record of ideas considered for empathySync - what shipped, what was rejected, and why. Not a roadmap. The roadmap tracks phases; this tracks thinking.

---

## Human Connection

### Smarter person matching when suggesting who to reach out to
**Status:** ✅ Shipped (Phase E3)
**What:** Instead of random selection from domain-filtered contacts, rank candidates by recency of contact, relationship type relevance to the current domain, and explicit domain tags. Show context ("Spoke 3 days ago") instead of generic relationship label.
**Why it fits:** empathySync's whole job is to redirect toward humans. The suggestion moment is the highest-value handoff point - making it specific and contextual increases the chance someone actually reaches out.

### Name interpolation in reach-out templates
**Status:** ✅ Shipped (Phase E3)
**What:** Templates personalised with the suggested person's first name - "Hey Sarah," instead of "Hey,"
**Why it fits:** Generic templates feel like form letters. One word change makes them feel like something the user actually wrote.

### Prompt builder for hard conversations
**Status:** ❌ Rejected
**What:** Help users craft prompts or scripts for difficult conversations (breakups, confrontations, apologies).
**Why not:** empathySync's role is to redirect people toward human connection, not to mediate or script those conversations. Building a tool that writes your hard conversation for you is the opposite of what this project is trying to do. The handoff templates already walk the line far enough.

### News/web integration for context-aware responses
**Status:** ❌ Rejected
**What:** Pull in current events or web content to give the AI more context when users mention news or world events.
**Why not:** Breaks the local-first principle. empathySync deliberately has no external calls. Adding a web fetch layer would also push the tool toward being a general-purpose assistant, which contradicts the core philosophy. If a user wants news analysis, a different tool does that better.

---

## Time and Usage

### Social media time tracking / per-site session limits
**Status:** ↗ Out of scope
**What:** Track how long users spend on specific sites; surface limits or friction when thresholds are hit.
**Why not here:** empathySync is a conversation tool, not a browser monitor. It has no access to what else the user is doing. This belongs in a browser extension that can observe tab behaviour, not in a chat interface. Building it here would require permissions and architecture that have nothing to do with empathySync's purpose.

---

## Interface

### CLI mode for power users
**Status:** ✅ Shipped (Phase 16)
**What:** `empathysync --mode cli` for terminal-first users who don't want Streamlit.
**Why it fits:** Same safety pipeline, different surface. Extracting `ConversationSession` made this straightforward without duplicating logic.

---

*Last updated: 2026-04-18*
