export default function PrototypeLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <>
      {/* Hide site chrome — prototypes are standalone */}
      <style dangerouslySetInnerHTML={{ __html: `
        nav[aria-label="Main navigation"],
        footer,
        button[aria-label="Send feedback"] { display: none !important; }
        main.flex-1 { margin: 0; padding: 0; }
      `}} />
      {children}
    </>
  )
}
