import SubscribeForm from './SubscribeForm'

/**
 * Full-width "Stay informed" CTA that visually breaks from meeting content.
 * Warm amber background + negative margins create a clear section divider.
 */
export default function SubscribeCTA() {
  return (
    <div className="relative -mx-4 sm:-mx-6 lg:-mx-8 my-10 bg-amber-50/60 border-y border-amber-200/40">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:gap-6">
          <div className="flex-1 mb-3 sm:mb-0">
            <h3 className="text-sm font-semibold text-civic-navy">
              Stay informed
            </h3>
            <p className="text-sm text-slate-600 mt-1 leading-relaxed">
              Get a briefing before and after each meeting.
            </p>
          </div>
          <div className="sm:w-80">
            <SubscribeForm compact />
          </div>
        </div>
      </div>
    </div>
  )
}
