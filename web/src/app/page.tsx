import { supabase } from '@/lib/supabase'

export default async function Home() {
  const { data, error } = await supabase
    .from('cities')
    .select('*')
    .eq('fips_code', '0660620')

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-red-600">
          <h1 className="text-2xl font-bold">Supabase Connection Error</h1>
          <pre className="mt-4">{JSON.stringify(error, null, 2)}</pre>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="max-w-xl">
        <h1 className="text-3xl font-bold mb-4">Richmond Transparency Project</h1>
        <p className="text-gray-600 mb-6">Supabase connection verified. City data:</p>
        <pre className="bg-gray-100 p-4 rounded text-sm overflow-auto">
          {JSON.stringify(data, null, 2)}
        </pre>
      </div>
    </div>
  )
}
