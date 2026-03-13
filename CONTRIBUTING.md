# Contributing to empathySync

Thank you for your interest in contributing to empathySync! This project exists to give users a privacy-respecting AI wellness tool that works for them, not against them.

## Development Principles

Before contributing, keep these principles in mind:

### 1. **Empathy First** 
- Every feature must center human wellbeing
- Build with the user's wellbeing in mind, not just technical correctness
- Test for emotional safety alongside technical functionality

### 2. **Privacy First**   
- All processing must remain local
- No external API calls without explicit user consent
- Data sovereignty is non-negotiable

### 3. **User Wellbeing** 
- Reject features that manipulate or exploit users
- Build technology that respects user autonomy
- Consider the wellness impact of your code

## Not an Engineer?

If you're a therapist, counsellor, social worker, UX writer, or ethicist - your expertise matters here more than code. See [HELP-SHAPE-THIS.md](HELP-SHAPE-THIS.md) for how to improve empathySync's responses, interventions, and connection-building guidance without writing any Python.

## Getting Started

1. **Fork the repository**
2. **Clone your fork**: `git clone https://github.com/your-username/empathySync.git`
3. **Create a virtual environment**: `python -m venv venv`
4. **Activate environment**: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
5. **Install dependencies**: `pip install -r requirements.txt`
6. **Copy .env.example to .env** and configure your settings
7. **Run tests**: `pytest tests/` (443 tests, all must pass)

## Development Workflow

1. **Create feature branch**: `git checkout -b feature/wellness-enhancement`
2. **Write tests first** (TDD approach)
3. **Implement with empathy**
4. **Test thoroughly** for both functionality and emotional safety
5. **Submit pull request** with detailed description

## Code Style

- Follow PEP 8 guidelines
- Use descriptive variable names that make your intent clear
- Comment code to explain the "why" behind empathetic choices
- Include docstrings for all functions

## Areas for Contribution

### **High Priority** 
- AI wellness conversation flows
- Emotional safety features  
- Local LLM optimization
- Accessibility improvements

### **Medium Priority** 
- UI/UX enhancements
- Documentation improvements
- Testing coverage
- Performance optimizations

### **Wellness Features** 
- Mindfulness exercise prompts
- Digital detox guidance
- Progress tracking features
- Community support tools

## Pull Request Guidelines

Your PR should include:

- **Clear description** of the change and why it serves users
- **Test coverage** for new functionality
- **Documentation updates** if needed
- **Emotional safety consideration** - how does this help users?

## Community Standards

- **Be kind** - Everyone is learning and growing
- **Assume good intent** - We're all here to serve users
- **Offer constructive feedback** - Help others improve
- **Respect boundaries** - Be mindful of people's time and contributions

## Required Reading

Before your first PR, please read:
- [MANIFESTO.md](MANIFESTO.md) - Non-negotiable design principles
- [CLAUDE.md](CLAUDE.md) - Technical architecture and safety pipeline
- [scenarios/README.md](scenarios/README.md) - If modifying the knowledge base

## Testing

Run the full test suite before submitting:
```bash
pytest tests/ -v
```

For changes to safety-critical code (crisis detection, dependency scoring), include specific test cases demonstrating the behavior.

---

*"Good tools get out of the way. Build something users can trust and then leave."*

**Thank you for helping people develop healthier relationships with AI.**
