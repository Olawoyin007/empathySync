# Scenarios Knowledge Base

This directory contains the structured knowledge base for empathySync's risk assessment, interventions, and response generation. All configuration is stored in YAML files for easy editing, version control, and community contribution.

## Directory Structure

```
scenarios/
├── config/               # System defaults and tunables (Phase 16.10)
│   └── system_defaults.yaml  # 100+ centralized settings (timeouts, turn limits, thresholds)
├── classification/       # LLM classifier prompts, config, avoidance phrases (Phase 9, 9.1, 25.4)
├── connection_building/  # Signposts and first-contact templates (Phase 12)
├── domains/              # 8 risk domains and their triggers
├── emotional_markers/    # Emotional intensity detection (4 levels)
├── emotional_weight/     # Task weight detection (high/medium/low)
├── graduation/           # Competence graduation prompts (Phase 3)
├── handoff/              # Human handoff templates (Phase 5)
├── intents/              # Session intent configuration (Phase 4)
├── interventions/        # Dependency, boundaries
├── metrics/              # Success metrics configuration (Phase 7)
├── prompts/              # Check-ins, mindfulness, styles
├── responses/            # Fallbacks, safe alternatives, base prompt
├── transparency/         # Explanation templates (Phase 6)
└── wisdom/               # Immunity building prompts (Phase 8)
```

## Quick Start

### Adding a New Domain Trigger

Edit `domains/<domain>.yaml` and add words to the `triggers` list:

```yaml
triggers:
  - existing_word
  - your_new_word
```

### Adding a New Check-in Prompt

Edit `prompts/check_ins.yaml` and add to the appropriate category:

```yaml
daily_check_ins:
  - "Your new check-in question?"
```

### Adding a Dependency Intervention Response

Edit `interventions/dependency.yaml` and add to the appropriate level:

```yaml
levels:
  - threshold: 5.0
    intervention:
      responses:
        - "Your new intervention message"
```

## File Reference

### domains/

Each domain file defines:
- `triggers`: Keywords that activate this domain
- `risk_weight`: Base risk score (0-10)
- `response_rules`: Instructions for the AI when this domain is active
- `redirects`: Pre-written responses for specific scenarios

**Files:**
- `crisis.yaml` - Suicidal ideation, self-harm (risk: 10.0)
- `harmful.yaml` - Illegal/violent intent (risk: 10.0)
- `health.yaml` - Medical concerns (risk: 7.0)
- `money.yaml` - Financial topics (risk: 6.0)
- `emotional.yaml` - General emotional expressions (risk: 5.0)
- `relationships.yaml` - Interpersonal dynamics (risk: 5.0)
- `spirituality.yaml` - Religious/spiritual matters (risk: 4.0)
- `logistics.yaml` - Neutral/default topics (risk: 1.0)

### emotional_markers/

Defines emotional intensity levels and their markers:
- `high_intensity.yaml` - Score 9.0, crisis-level emotions
- `medium_intensity.yaml` - Score 6.0, significant distress
- `low_intensity.yaml` - Score 4.0, mild emotional coloring
- `neutral.yaml` - Score 3.0, default state

### interventions/

Defines intervention strategies:
- `dependency.yaml` - Graduated responses for dependency patterns
- `session_boundaries.yaml` - Time and frequency limits
- `graduation.yaml` - Skill-building to reduce reliance

### prompts/

User-facing prompts and AI styles:
- `check_ins.yaml` - Reflection prompts by category
- `mindfulness.yaml` - Digital wellness prompts
- `styles.yaml` - Gentle/Direct/Balanced modifiers

### responses/

Response templates:
- `fallbacks.yaml` - When AI can't generate suitable response
- `safe_alternatives.yaml` - When response contains harmful patterns
- `base_prompt.yaml` - Core system prompt configuration

### classification/

LLM classifier configuration (Phase 9, 9.1):
- `llm_classifier.yaml` - Classification prompt template, examples, and fast-path patterns
- `avoidance.yaml` - (Phase 25.4) Substitution phrases: the app being chosen over
  a real action

**Editing `avoidance.yaml`:** it holds two lists and **both must match** for the
check to fire. `chat_as_destination` is the conversation being named as where the
user intends to stay ("stay here", "with you", "keep me company").
`obligation_displaced` is a real-world action being set aside ("don't have to",
"than actually", "forget the", "avoiding").

Each half alone is ordinary English, which is why one list is not enough: *"I'd
rather use Python than Java"* displaces something with no chat in it, and *"let's
keep going"* names the chat with nothing displaced. Matching either half on its
own routes ordinary coding questions into restraint.

So when adding a phrase, put it in the list it actually belongs to, and keep
generic continuations ("keep going", "carry on") out of `chat_as_destination`
entirely - they appear in normal task requests.

**Key fields in classification output:**
- `domain` - One of 8 domains (crisis, harmful, health, money, emotional, relationships, spirituality, logistics)
- `emotional_intensity` - 0-10 scale
- `is_personal_distress` - Whether user is personally distressed
- `is_practical_technique` - (Phase 9.1) Whether user is asking "how to" vs "should I"
- `confidence` - 0-1 confidence score

**Practical Technique Detection (Phase 9.1):**

The `is_practical_technique` field distinguishes:
- **Technique questions** → Practical Mode (full help): "How do I meditate?", "What are budgeting methods?"
- **Guidance questions** → Reflective Mode (restraint): "Should I get this surgery?", "Is this God's will?"

To add classification examples, edit `llm_classifier.yaml`:

```yaml
examples:
  - message: "How do I meditate for beginners?"
    classification:
      domain: "spirituality"
      emotional_intensity: 1
      is_personal_distress: false
      is_practical_technique: true  # Technique question → Practical Mode
      confidence: 0.95
    explanation: "Asking for meditation technique, not spiritual guidance"

  - message: "Is this my spiritual calling?"
    classification:
      domain: "spirituality"
      emotional_intensity: 6
      is_personal_distress: true
      is_practical_technique: false  # Guidance question → Reflective Mode
      confidence: 0.9
    explanation: "Seeking spiritual direction, needs human support"
```

### connection_building/

Connection building resources for users with empty or limited trusted networks (Phase 12):
- `signposts.yaml` - Types of places to find human connection (no specific services, just categories)
- `first_contact.yaml` - Templates for initiating new connections

**Signposts** are organized into:
- **General categories**: Community groups, volunteering, support groups, classes, religious communities
- **Domain-specific categories**: Tailored suggestions when user is dealing with specific topics (relationships, money, health, spirituality, emotional)
- **Reflection prompts**: Help users identify where they might find their people
- **Encouragement messages**: Acknowledge that building connection is hard

**First-contact templates** cover 5 situations:
- Starting a conversation at a group or meetup
- Turning an acquaintance into a friend
- Reconnecting with someone from the past
- Joining a new community
- Asking someone for help

To add a new signpost category, edit `signposts.yaml`:

```yaml
general_signposts:
  - category: "Your new category"
    description: "What kinds of groups/activities this includes"
    why_it_works: "Why this helps build connection"
    search_hint: "How to find this locally"
```

To add domain-specific signposts:

```yaml
domain_signposts:
  your_domain:
    intro: "Context-setting message for this domain"
    categories:
      - category: "Specific category"
        examples: "Concrete examples"
        search_hint: "How to search"
```

To add a new first-contact situation, edit `first_contact.yaml`:

```yaml
situations:
  your_situation:
    title: "Situation title"
    intro: "Brief intro text"
    templates:
      - template: "Example message or opener"
        context: "When to use this"
    tips:
      - "Practical advice"
```

## Contributing New Scenarios

### Guidelines

1. **Align with the Manifesto**: All additions must support human autonomy and psychological safety
2. **Test locally**: Run `pytest tests/` after changes
3. **Be specific**: Vague triggers cause false positives
4. **Include context**: Add descriptions explaining why a trigger/response exists

### Adding a New Domain

1. Create `domains/your_domain.yaml`:

```yaml
domain: your_domain
risk_weight: 5.0  # 0-10 scale
description: Brief description of this domain

triggers:
  - keyword1
  - keyword2

response_rules:
  - "Rule for AI behavior"
  - "Another rule"

redirects:
  scenario_name:
    trigger_phrases:
      - "specific phrase to match"
    response: "Pre-written response for this scenario"
```

2. The ScenarioLoader will automatically pick up the new file

### Adding Emotional Markers

Add to the appropriate intensity file or create a new level:

```yaml
intensity_level: your_level
score: 5.0  # 0-10 scale

markers:
  - emotion_word
  - another_emotion

response_modifier: |
  Instructions for AI when this intensity is detected.
```

## Hot Reloading

The ScenarioLoader supports hot reloading for development:

```python
from utils.scenario_loader import get_scenario_loader

loader = get_scenario_loader()
loader.reload()  # Picks up changes from disk
```

## Validation

Before committing changes, verify your YAML is valid:

```bash
python -c "import yaml; yaml.safe_load(open('scenarios/domains/your_file.yaml'))"
```

## Safety Notes

- **Crisis and Harmful domains are special**: Changes to these require extra review
- **Test edge cases**: Ensure triggers don't false-positive on safe content
- **Preserve redirects**: Don't remove crisis hotline information
- **No engagement optimization**: Never add features that increase usage

## Examples

### Good Trigger Words
```yaml
# Specific, unlikely to false-positive
- "bankruptcy"
- "panic attack"
- "kill myself"
```

### Bad Trigger Words
```yaml
# Too vague, will false-positive
- "bad"      # Could match "not bad", "bad weather"
- "help"     # Could match "help me understand"
- "need"     # Too common
```

### Good Response Rules
```yaml
response_rules:
  - "Do NOT give financial advice"  # Clear prohibition
  - "Redirect to professional"       # Clear action
```

### Bad Response Rules
```yaml
response_rules:
  - "Be careful"        # Too vague
  - "Use good judgment" # Not actionable
```
