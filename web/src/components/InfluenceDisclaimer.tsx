/**
 * InfluenceDisclaimer — S14 C4
 *
 * Multi-level disclaimer system for influence map pages.
 * These are NOT optional — they are a core part of the design.
 *
 * The disclaimers exist because showing a campaign contribution alongside
 * a vote, without context, structurally implies causation even when none
 * is stated. Research C (defamation by implication) identified this as the
 * single most criticized pattern in civic transparency tools.
 */

interface DisclaimerProps {
  variant: 'campaign' | 'behested' | 'confidence'
}

export function CampaignFinanceDisclaimer() {
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-4">
      <p className="text-sm font-medium text-slate-700 mb-2">About this data</p>
      <p className="text-sm text-slate-600 leading-relaxed mb-2">
        Richmond Common presents campaign finance information compiled from
        official public records filed with NetFile (City of Richmond),
        CAL-ACCESS (California Secretary of State), and the FPPC. All source
        data is public under California Government Code §81008.
      </p>
      <p className="text-sm text-slate-700 leading-relaxed font-medium">
        A campaign contribution does not imply wrongdoing.
      </p>
      <p className="text-sm text-slate-600 leading-relaxed">
        Showing that a contributor gave to a council member&apos;s campaign alongside
        that member&apos;s voting record identifies a publicly documented financial
        relationship — it does not suggest the contribution caused or influenced
        the vote. Campaign contributions are one of many factors in legislative decisions.
      </p>
    </div>
  )
}

export function BehstedPaymentDisclaimer() {
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-4">
      <p className="text-sm font-medium text-slate-700 mb-2">About behested payments</p>
      <p className="text-sm text-slate-600 leading-relaxed mb-2">
        A behested payment is a payment made to a third party (usually a nonprofit
        or community organization) at the request of an elected official. California
        law (Government Code §82015) requires officials to disclose these requests
        when the total reaches $5,000 or more.
      </p>
      <p className="text-sm text-slate-700 leading-relaxed font-medium">
        A behested payment disclosure does not imply wrongdoing.
      </p>
      <p className="text-sm text-slate-600 leading-relaxed">
        It documents that an official directed funds toward a specific cause or
        organization. The official does not personally receive the payment. Behested
        payments are one of many ways elected officials support community organizations
        and programs.
      </p>
    </div>
  )
}

export function ConfidenceExplanation() {
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-4">
      <p className="text-sm font-medium text-slate-700 mb-2">What confidence scores mean</p>
      <p className="text-sm text-slate-600 leading-relaxed">
        Our confidence score reflects how certain we are that we have correctly
        matched public records to the right person or entity. A score of 90%+
        means the match is highly reliable based on name, address, and ID number
        matching. The score does <em>not</em> measure the likelihood that a
        contribution influenced a decision.
      </p>
    </div>
  )
}

export default function InfluenceDisclaimer({ variant }: DisclaimerProps) {
  switch (variant) {
    case 'campaign':
      return <CampaignFinanceDisclaimer />
    case 'behested':
      return <BehstedPaymentDisclaimer />
    case 'confidence':
      return <ConfidenceExplanation />
  }
}
