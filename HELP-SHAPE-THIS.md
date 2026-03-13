# Help Shape empathySync -No Coding Required

empathySync is built on a simple belief: AI should help people leave and go live their lives, not keep them talking.

The engineers built the structure. But whether the words actually land -whether a response to "I feel lonely" feels human or hollow -that's not an engineering question. That's your question.

If you're a therapist, counsellor, social worker, UX writer, ethicist, or someone who simply notices when language doesn't ring true, your input here matters more than code ever could.

---

## What you can improve

### The words empathySync says when someone is struggling

When someone types "I feel lonely" or "I'm overwhelmed," empathySync gives a brief response and gently redirects them toward a real person. Right now those responses were written by engineers. They're functional. They could be much better.

**→ [View and suggest improvements to emotional responses](scenarios/domains/emotional.yaml)**

Look for the `redirects:` section -that's what the user actually sees.

---

### What it says about relationship pain

When someone asks "should I leave him?" or "what does she mean by that?" -empathySync deliberately refuses to answer and redirects. The *way* it refuses matters enormously. Too cold and the person feels dismissed. Too warm and it becomes the thing it's trying not to be.

**→ [View and suggest improvements to relationship responses](scenarios/domains/relationships.yaml)**

---

### The messages it sends when someone is coming back too often

empathySync tracks when someone is returning too frequently and intervenes. There are five levels -from a quiet nudge to a firm pause. These messages carry real weight. They need to feel honest and caring, not clinical.

**→ [View and suggest improvements to dependency intervention messages](scenarios/interventions/dependency.yaml)**

Look for the `responses:` lists under each level. That's what the user reads.

---

### Guidance for people who have no one to talk to

When empathySync redirects someone to "talk to a real person" and that person has nobody -it can't just leave them there. This file contains categories of places people can find genuine connection. Are the descriptions right? Is anything missing?

**→ [View and suggest improvements to connection-building guidance](scenarios/connection_building/signposts.yaml)**

---

### Scripts for reaching out when you don't know what to say

Some users want to reconnect with someone, or reach out to a new community, but can't find the words. This file has conversation starters for those moments. A social worker would immediately see what's missing.

**→ [View and suggest improvements to first-contact templates](scenarios/connection_building/first_contact.yaml)**

---

### Crisis helpline numbers for your country

When someone is in crisis, empathySync shows helpline numbers immediately. If your country is missing, or a number is wrong, fixing it takes thirty seconds and could matter enormously.

**→ [View and add crisis resources by country](scenarios/domains/crisis.yaml)**

Scroll to `regional_resources:` -the format is just a name, a phone number, and whether it's a call or text line.

---

## How to suggest a change

You don't need to install anything or learn any tools.

1. Click any of the file links above
2. You'll see the file on GitHub -the text is plain and readable
3. Click the pencil icon at the top right of the file
4. Edit the words you want to change (the structure around them can stay as-is)
5. At the bottom, write a sentence about what you changed and why
6. Click **Propose changes** -GitHub handles the rest

Someone from the project will review it before anything goes live. You won't break anything.

**Prefer not to edit directly?** Just open a conversation at [github.com/Olawoyin007/empathySync/issues](https://github.com/Olawoyin007/empathySync/issues) and describe what you noticed. Write it however feels natural -a paragraph is enough.

---

## What good feedback looks like

The most valuable contributions come from someone who reads a response and thinks *that's not how a person actually talks* or *that word would land very differently on someone who's already struggling.*

You don't need to know the right answer. Pointing at what doesn't feel right is enough to start a conversation.

---

*The engineers build the structure. You bring the real-world knowledge to make it work.*
