import SubscribeForm from './SubscribeForm'

/**
 * Inline "Stay informed" CTA for embedding in content pages.
 * Uses the compact SubscribeForm variant (email-only, horizontal layout).
 */
export default function SubscribeCTA() {
  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-5 my-8">
      <div className="flex flex-col sm:flex-row sm:items-start sm:gap-6">
        <div className="flex-1 mb-3 sm:mb-0">
          <h3 className="text-sm font-semibold text-civic-navy">
            Stay informed
          </h3>
          <p className="text-sm text-slate-600 mt-1 leading-relaxed">
            Get a briefing before and after each City Council meeting. Plain
            language, sourced from public records.
          </p>
        </div>
        <div className="sm:w-80">
          <SubscribeForm compact />
        </div>
      </div>
    </div>
  )
}
