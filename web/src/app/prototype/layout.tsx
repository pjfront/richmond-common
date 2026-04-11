import Link from 'next/link'

export default function PrototypeLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className="min-h-screen bg-white">
      <div className="max-w-[640px] mx-auto px-5">
        <nav className="pt-4 pb-2 flex items-center justify-between text-sm" style={{ fontFamily: 'Georgia, "Times New Roman", serif' }}>
          <Link href="/prototype" className="text-neutral-400 hover:text-neutral-600 transition-colors">
            &larr; Prototypes
          </Link>
          <span className="text-neutral-300 text-xs tracking-widest uppercase">Prototype</span>
        </nav>
      </div>
      {children}
    </div>
  )
}
