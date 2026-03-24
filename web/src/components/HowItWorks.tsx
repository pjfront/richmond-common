const steps = [
  {
    number: '1',
    title: 'Ingest',
    description:
      'We automatically download agendas, minutes, staff reports, and campaign finance filings from official government sources.',
  },
  {
    number: '2',
    title: 'Analyze',
    description:
      'Structured data extracted from documents, then cross-referenced against campaign contributions and financial disclosures.',
  },
  {
    number: '3',
    title: 'Publish',
    description:
      'Financial contribution reports are generated before each meeting, cross-referencing campaign finance records with agenda items.',
  },
]

export default function HowItWorks() {
  return (
    <div>
      <h2 className="text-xl font-semibold text-slate-800 mb-6 text-center">How It Works</h2>
      <div className="grid sm:grid-cols-3 gap-6">
        {steps.map((step) => (
          <div key={step.number} className="text-center">
            <div className="w-10 h-10 rounded-full bg-civic-navy text-white flex items-center justify-center font-bold text-lg mx-auto mb-3">
              {step.number}
            </div>
            <h3 className="font-semibold text-slate-800 mb-2">{step.title}</h3>
            <p className="text-sm text-slate-600 leading-relaxed">{step.description}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
