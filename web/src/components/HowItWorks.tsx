const steps = [
  {
    number: '1',
    title: 'Collect',
    description:
      'We pull agendas, minutes, votes, and public comments from Richmond\u2019s official meeting portals \u2014 21 years of city council records.',
  },
  {
    number: '2',
    title: 'Translate',
    description:
      'Every agenda item gets a plain language summary so you can understand what\u2019s being decided without reading hundreds of pages of government documents.',
  },
  {
    number: '3',
    title: 'Connect',
    description:
      'Council member profiles, voting records, and meeting history are linked together so you can follow who voted on what and what the community had to say.',
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
