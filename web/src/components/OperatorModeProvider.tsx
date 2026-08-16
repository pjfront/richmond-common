'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { probeOperatorSession } from '@/lib/operator-session-probe'

interface OperatorModeContextValue {
  isOperator: boolean
  isOperatorResolved: boolean
}

const OperatorModeContext = createContext<OperatorModeContextValue>({
  isOperator: false,
  isOperatorResolved: false,
})

export function useOperatorMode() {
  return useContext(OperatorModeContext)
}

export function OperatorModeProvider({ children }: { children: ReactNode }) {
  const [isOperator, setIsOperator] = useState(false)
  const [isOperatorResolved, setIsOperatorResolved] = useState(false)

  useEffect(() => {
    let cancelled = false
    probeOperatorSession().then((resolvedState) => {
      if (!cancelled && resolvedState !== null) {
        setIsOperator(resolvedState)
        setIsOperatorResolved(true)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <OperatorModeContext.Provider value={{ isOperator, isOperatorResolved }}>
      {children}
    </OperatorModeContext.Provider>
  )
}
