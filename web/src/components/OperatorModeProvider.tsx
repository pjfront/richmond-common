'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface OperatorModeContextValue {
  isOperator: boolean
}

const OperatorModeContext = createContext<OperatorModeContextValue>({ isOperator: false })

export function useOperatorMode() {
  return useContext(OperatorModeContext)
}

export function OperatorModeProvider({ children }: { children: ReactNode }) {
  const [isOperator, setIsOperator] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch('/api/operator/session', { credentials: 'same-origin', cache: 'no-store' })
      .then((res) => (res.ok ? res.json() : { isOperator: false }))
      .then((data: { isOperator?: boolean }) => {
        if (!cancelled) setIsOperator(data.isOperator === true)
      })
      .catch(() => {
        if (!cancelled) setIsOperator(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <OperatorModeContext.Provider value={{ isOperator }}>
      {children}
    </OperatorModeContext.Provider>
  )
}
