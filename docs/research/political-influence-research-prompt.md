# Deep Research Prompt: Political Influence Tracing via Public Records

*For use in Claude Chat with deep research enabled. Copy everything below the line.*

---

## Prompt

I'm building a local government transparency platform that automatically analyzes public records to detect potential conflicts of interest and political influence patterns. The platform currently tracks:

- **City council meeting minutes** (votes, motions, agenda items)
- **Campaign finance contributions** (who donated to whom, how much)
- **Form 700 financial disclosures** (officials' financial interests)
- **City expenditures** (vendor payments, contracts)
- **City employee payroll** (salaries, hierarchy, departments)

I want to expand into tracking **regulatory and administrative actions** that can be influenced politically, and cross-referencing them against the financial/political data above. The pilot city is Richmond, California, but the system is designed to scale to any US city.

### What I need you to research:

**1. Forms of political influence traceable through public records**

What are the documented patterns of political influence, manipulation, and abuse at the local government level that leave traces in publicly available records? I'm not interested in speculation. I want patterns that have been documented in investigative journalism, academic research, government audits, or legal proceedings. For each pattern, tell me:
- What the pattern looks like
- What public records would reveal it
- How common it is at the municipal level
- Notable examples (city name, year, what happened)

**2. Regulatory and administrative data sources**

For each of these categories, what public records exist, what platforms/portals typically host them, and what fields would be most useful for cross-referencing against political connections:
- Building permits and planning approvals
- Business licenses and renewals
- Code enforcement actions and violations
- Zoning variances and conditional use permits
- City contracts and procurement (beyond simple expenditure data)
- Property transactions involving city-adjacent entities
- Environmental permits and compliance actions
- Liquor licenses and cannabis permits (where applicable)
- Inspection records (building, fire, health)

**3. Entity resolution data sources**

To connect the dots, I need to know who controls what. What public registries exist for:
- Corporate ownership and officers (state-level business filings)
- LLC membership (which states require disclosure vs. which allow anonymity)
- Nonprofit officers and boards (IRS 990 data, state AG filings)
- Property ownership (county assessor/recorder data)
- Professional licenses (contractors, real estate, etc.)
- Lobbyist registrations (city and state level)

For each, tell me: where the data lives, whether it has an API or bulk download, how often it's updated, and what the key linking fields are (names, addresses, EINs, etc.).

**4. Cross-referencing patterns**

What are the highest-signal cross-references? If I could only build 5 cross-reference checks, which combinations of data sources would catch the most documented patterns of influence? Rank them by:
- Signal strength (how often a match indicates actual influence vs. coincidence)
- Data availability (how easy is the data to obtain programmatically)
- Legal clarity (is flagging this pattern defensible, or does it risk defamation concerns)

**5. What others have built**

What existing tools, platforms, or research projects have attempted similar cross-referencing of political influence at the local level? What worked, what didn't, and what can I learn from them? I'm particularly interested in:
- Open-source tools or datasets
- Academic research on municipal corruption detection
- Investigative journalism methodologies (especially computational/data journalism)
- Government audit methodologies (state auditors, inspectors general)

### Constraints on my platform:
- Everything must be based on public records. No surveillance, no private data.
- The platform is a governance assistant, not an adversarial watchdog.
- All findings include confidence scores. Nothing is presented as fact without sourcing.
- The operator (me) sits on a city board. The framing must be collaborative, not accusatory.
- The system flags patterns for human review. It never makes accusations.

### Output format:
Please organize your findings into clear sections matching my 5 questions above. For each data source, include specific URLs, API documentation links, or platform names where possible. Distinguish between what's available nationally vs. California-specific vs. Richmond-specific. When citing examples, include enough detail that I could verify them independently.
