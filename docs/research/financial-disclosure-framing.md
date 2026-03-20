# Financial Disclosure Framing: Legal Standards, Risks, and Best Practices

**Richmond Common's Influence Map operates on exceptionally strong legal ground.** California Government Code §81008 imposes "no conditions whatsoever" on persons inspecting or reproducing campaign finance filings — among the strongest public access language in any U.S. state statute. No major transparency organization has faced a successful defamation lawsuit for presenting campaign finance data. The primary risk is not legal liability but *credibility damage* from framing that implies causation between donations and votes, which cognitive science research shows is how citizens naturally interpret juxtaposed financial-political data. The project's "governance assistant, not adversarial watchdog" framing is not just a brand choice — it is the single most important legal and ethical safeguard for the Influence Map.

---

## California law provides an exceptionally permissive foundation

The California Political Reform Act creates a layered legal framework that actively supports third-party platforms presenting campaign finance data. The critical statute is **Government Code §81008**, which states:

> *"No conditions whatsoever shall be imposed upon persons desiring to inspect or reproduce reports and statements filed under this title, nor shall any information or identification be required from these persons."*

This language is extraordinarily broad. It imposes no restrictions on purpose, format, or subsequent use. The Act's stated purpose in **§81002** explicitly declares that "receipts and expenditures in election campaigns should be fully and truthfully disclosed in order that the voters may be fully informed." A civic platform presenting this data directly furthers the legislature's stated intent.

**No FPPC regulation, advisory opinion, or guidance document addresses how third parties may present campaign finance data.** After thorough searching, this regulatory gap is itself significant: the FPPC regulates filers, not publishers. The Commission's posture is overwhelmingly pro-transparency — it publishes Form 700s in a searchable online portal, links to the privately developed Power Search tool on the Secretary of State's site, and AB 2151 (§84616) mandates local agencies post filings online within 72 hours.

Multiple layers of California law protect a platform like Richmond Common:

- **Fair report privilege** (Civil Code §47(d) and (e)) — protects "fair and true" reports of public official proceedings and publications "for the public benefit"
- **Anti-SLAPP statute** (Code of Civil Procedure §425.16) — allows early dismissal of meritless lawsuits targeting public-interest speech, with mandatory attorney's fee awards to prevailing defendants
- **Public figure doctrine** — elected officials must prove "actual malice" (knowledge of falsity or reckless disregard for truth) under *New York Times v. Sullivan*
- **Truth as absolute defense** — accurately reporting public records is inherently protected
- **California Public Records Act** (Gov. Code §7920.000+) — declares access to public records a "fundamental and necessary right" with no use restrictions after records are obtained

At the federal level, the FEC's regulation at **11 CFR §104.15(c)** explicitly permits use of campaign finance data "in newspapers, magazines, books or other similar communications" as long as the principal purpose is not solicitation. The Second Circuit's ruling in *FEC v. Political Contributions Data, Inc.* (943 F.2d 190, 1991) held that even a for-profit company compiling and selling FEC contributor data fell within this media/publication exemption. The court noted that "profound First Amendment difficulties would arise if we attempted to ban the publication of donor information."

**One notable restriction**: §84602 requires government agencies to redact street addresses and bank account numbers from online postings. While this requirement explicitly applies to government agencies rather than third parties, Richmond Common should follow the same practice as a matter of prudence and good faith.

---

## The real risk is defamation by implication, not data republication

No major transparency organization — not OpenSecrets, MapLight, Sunlight Foundation, nor any similar entity — has been sued for defamation based on how it presented campaign finance data. This absence reflects the strong legal protections described above. However, the **legal doctrine of defamation by implication** represents a real, if low-probability, risk for the Influence Map's specific donation-to-vote juxtaposition format.

**Defamation by implication** occurs when literally true facts create a false impression through juxtaposition or omission. The Texas Supreme Court articulated this in *Dallas Morning News v. Tatum* (2018): "a publication's gist can be false through the omission or juxtaposition of facts, even though the publication's individual statements considered in isolation are literally true." Most jurisdictions apply a heightened standard requiring that the platform *intended or endorsed* the defamatory inference — not merely that a reader could draw one.

The critical legal distinction for the Influence Map is between three tiers of framing:

- **SAFE**: "NetFile records show Acme Development PAC contributed $4,200 to Martinez's campaign committee across 3 contributions between 2022-2024." (Factual, sourced, neutral — fully protected by fair report privilege.)
- **MODERATE RISK**: "Council Member Martinez voted yes. His campaign received $4,200 from Acme Development PAC." (Juxtaposition implies connection but does not assert causation. Defensible with proper disclaimers.)
- **HIGH RISK**: "Martinez's vote was funded by Acme Development" or "Martinez has financial ties to Acme Development." (Implies quid pro quo or personal financial benefit — language that goes beyond what the records show.)

The phrase "financial connection" in the current Influence Map framing warrants scrutiny. **"X donated to Y's campaign"** is a verifiable statement of fact. **"X has a financial connection to Y"** is broader and more ambiguous — it could imply personal financial benefit, corruption, or undisclosed relationships beyond a campaign donation. The safer construction is the former.

**MapLight's experience is the most instructive precedent.** The Institute for Free Speech criticized MapLight's "Money Near Votes" tool as "at best useless and at worst misleading" for three specific deficiencies: (1) it showed no voting pattern context — whether legislators typically voted with the highlighted industry's interests regardless of donations; (2) it provided no relative contribution size — whether the donation was 50% or 0.1% of total fundraising; and (3) it highlighted temporal proximity between donations and votes without acknowledging that Congress considers many bills simultaneously. These are *exactly* the contextual gaps Richmond Common must address.

---

## Cognitive science shows narrative framing amplifies implied causation

No controlled study directly compares narrative versus tabular presentation of campaign finance data — this is a genuine gap in the literature. However, adjacent cognitive science research strongly suggests that **the Influence Map's plain-language sentence format carries higher misinterpretation risk than tabular data.**

Three cognitive biases are particularly relevant. **Illusory correlation** (Chapman, 1967) causes people to perceive relationships between variables when none exist — juxtaposing a large donation with a controversial vote creates a memorable pairing that readers overinterpret. **Confirmation bias** ensures citizens viewing campaign finance data interpret donation-vote juxtapositions in ways that confirm their prior political beliefs, with MRI studies showing emotional processing centers override rational evaluation. **The availability heuristic** (Tversky & Kahneman, 1973) means that vivid narrative framing ("Big developer donated $4,200, then the council member voted yes on the project") creates easily recalled associations that inflate perceived significance.

Harvard's Ash Center research, particularly Archon Fung, Mary Graham, and David Weil's *Full Disclosure: The Perils and Promise of Transparency* (2007), found that transparency information is "often incomplete, incomprehensible, or irrelevant to consumers" and that effective systems must provide "easily used information" with "accurate and comparable metrics." Their critical insight: **"More public information is not necessarily better"** — systems can "confuse information users so that their choices become counter-productive."

Research on citizen responses to campaign finance disclosure paints a nuanced picture. Spencer and Theodoridis (2016) found that most respondents perceived "many common behaviors besides bribery to be 'very corrupt'" — suggesting a baseline public predisposition to infer corruption. A *Political Behavior* study (2021) found that campaign finance information CAN affect vote choice when presented alone, but effects are **"swamped" by other political signals** like ideology and partisanship.

For the Influence Map's confidence scores, research from van der Bles et al. (2020, PNAS) found that **numerical ranges with point estimates** preserve trust better than verbal hedging. Verbal uncertainty statements ("there may be some uncertainty") actually *decreased* trust in both the data and the source. The Cambridge Winton Centre confirmed that graphical representations of uncertainty maintain trust better than verbal ones. This supports using percentage-based confidence scores (Strong ≥85%, Moderate 70-85%, Low <70%) but argues for presenting them numerically rather than with hedging language.

---

## What the established platforms actually say in their disclaimers

**MapLight's disclaimer is the gold standard** for the Influence Map's use case, because MapLight specifically mapped connections between donations and legislative votes:

> *"The correlations we highlight between industry and union giving and legislative outcomes do not show that one caused the other, and we do not make this claim."*

MapLight also included: *"Campaign finance data is subject to continual updates because of amended filings, contribution refunds, and other aspects of the filing and data collection processes."*

**OpenSecrets** takes a more measured approach: *"We know that not every contribution is made with the donor's economic or professional interests in mind, nor do we assert that every donor considers their employer's interests when they make a contribution."* Their donor lookup pages include the federal disclaimer: *"Federal law prohibits the use of contributor information for the purpose of soliciting contributions or for any commercial purpose."*

**Follow The Money** frames its data as educational: *"Information provided by the Institute—on its website, in custom files, or via NIMP APIs—is meant for research or educational purposes only."*

**Transparent California**, the closest California-specific analogue, states: *"All data on Transparent California has been compiled from public records requested and received from the associated political entity and is provided as a public service. We are not responsible for errors contained in those public records."*

**CAL-ACCESS** (the state's own system) disclaims accuracy: *"The California Secretary of State makes no claims, promises, or guarantees about the absolute accuracy, completeness, or adequacy of the contents of this website."*

Seven patterns appear consistently across all established platforms:

1. **Correlation ≠ causation** — explicitly stated where donations are shown alongside votes or outcomes
2. **Data source attribution** — always citing official government sources
3. **No warranty / as-is language** — standard legal disclaimers about data accuracy
4. **Data freshness warnings** — noting that filings are amended and updated over time
5. **Anti-solicitation notices** — prohibiting use of contributor data for fundraising
6. **Methodology transparency** — explaining how data is aggregated, matched, and categorized
7. **Nonpartisan purpose statement** — clarifying the platform serves civic/educational purposes

No established platform uses "confidence scores" for financial connections. This is a novel feature for Richmond Common, which means there is no industry standard to follow — but also no precedent suggesting it is problematic. The approach of quantifying match certainty is actually more transparent than what most platforms do (silently present matched data without acknowledging uncertainty in matching).

---

## Practical recommendations and draft disclaimer text

### Recommended language changes for the Influence Map

**Replace "financial connection" with "campaign finance relationship" or "campaign contribution record."** The word "connection" implies a broader relationship than a campaign donation; "contribution record" is precise and defensible.

**Replace the example sentence format.** The current format — "Council Member Martinez voted yes. His campaign received $4,200 from Acme Development PAC" — juxtaposes vote and donation in a way that implies causation. A safer construction separates the data elements and leads with the source:

> *"According to NetFile filings, Acme Development PAC made 3 contributions totaling $4,200 to the Martinez campaign committee between 2022-2024. Council Member Martinez voted yes on [item]. Multiple factors influence any council vote."*

**Add contextual data to every connection.** The single most actionable lesson from MapLight's criticism is that showing a donation next to a vote *without context* is misleading. For each connection shown, include:

- The donation as a percentage of the official's total campaign fundraising
- The total number of contributions from all sources during the same period
- Whether the official voted *against* the contributor's apparent interest on other occasions
- Whether other council members who received no contributions from this source voted the same way

### Draft disclaimer text

**Global disclaimer (appears on the Influence Map landing page):**

> **About this data**: Richmond Common presents campaign finance information compiled from official public records filed with NetFile (City of Richmond), CAL-ACCESS (California Secretary of State), and the FPPC. All source data is public under California Government Code §81008.
>
> **A campaign contribution does not imply wrongdoing.** Showing that a contributor gave to a council member's campaign alongside that member's voting record identifies a publicly documented financial relationship — it does not suggest the contribution caused or influenced the vote. Campaign contributions are one of many factors in legislative decisions, and academic research finds no systematic evidence of a direct causal link between donations and votes.
>
> This tool is a governance assistant designed to make existing public records more accessible. Data is subject to change as filings are amended. Confidence scores reflect our certainty in matching contributor records to specific entities and do not indicate likelihood of influence. We encourage users to review original source filings linked from each record.

**Per-connection disclaimer (appears in tooltip or expandable text on each connection):**

> This information comes from public campaign finance filings. A contribution to a campaign does not imply that the contributor influenced the officeholder's decisions. [View original filing →]

**Confidence score explanation (appears once per page where scores are shown):**

> **What confidence scores mean**: Our confidence score reflects how certain we are that we have correctly matched public records to the right person or entity — for example, that "Acme Development PAC" in one filing is the same entity as "Acme Dev PAC" in another. A score of 90%+ means the match is highly reliable based on name, address, and ID number matching. The score does *not* measure the likelihood that a contribution influenced a decision.

### What to avoid

- **Never use "financial connection" or "financial ties"** — these imply relationships beyond documented campaign contributions
- **Never use "funded," "bankrolled," "backed by," or "paid for"** — these imply quid pro quo
- **Never show donation-vote pairs without context** — always include total fundraising figures, the number of other council members who voted the same way, and the contributor's share of total contributions
- **Never omit cases where an official voted against a contributor's interest** — cherry-picking only aligned votes is the most criticized practice in the transparency field
- **Never lead with the vote, then show the donation** — this framing ("Martinez voted yes → he received $4,200 from Acme") structurally implies the vote was a consequence. Lead with the contribution record instead
- **Avoid verbal uncertainty hedges** like "may" or "possibly" in confidence descriptions — research shows these decrease trust. Use numerical scores instead

### Where disclaimers should appear

Based on established platform practices and cognitive science research on the deterministic construal error (where users treat data as certain unless uncertainty is prominently communicated):

- **Global disclaimer**: On every page that displays Influence Map data, above the data, not buried in a footer
- **Per-connection tooltip**: On every individual connection, accessible via an info icon (ℹ️) or expandable text
- **Confidence score explanation**: Once per page, linked from every confidence badge
- **Methodology page**: Comprehensive documentation of data sources, matching algorithms, confidence score calculations, and known limitations — linked from every Influence Map page
- **Source links**: Every data point should link to the original filing on NetFile or CAL-ACCESS

---

## Conclusion

Richmond Common's Influence Map is legally well-protected under California law — the combination of §81008's unconditional access provision, anti-SLAPP protections, fair report privilege, and the actual malice standard for public officials creates a robust defensive posture. The real risk is reputational, not legal. MapLight's experience demonstrates that a transparency tool can be technically accurate yet widely criticized as misleading if it juxtaposes donations and votes without sufficient context.

The project's "governance assistant" framing is its strongest asset. Three design choices will determine whether the Influence Map builds trust or erodes it: **(1) always providing contextual data** — contribution as a percentage of total fundraising, whether other members voted the same way, and the contributor's full giving pattern; **(2) leading with source attribution** rather than implied narrative; and **(3) maintaining a clear, visible separation between what public records show and what users might infer.** The confidence score system is genuinely novel in this space and, if explained clearly using numerical rather than verbal framing, could become a model for other civic transparency platforms. The draft disclaimer language above is designed to be legally protective, civically responsible, and consistent with the collaborative relationship the project maintains with Richmond city government.