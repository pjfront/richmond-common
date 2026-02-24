'use client'

import { useOperatorMode } from './OperatorModeProvider'
import type { ReactNode } from 'react'

interface OperatorGateProps {
  children: ReactNode
  fallback?: ReactNode
}

export default function OperatorGate({ children, fallback = null }: OperatorGateProps) {
  const { isOperator } = useOperatorMode()
  if (!isOperator) return <>{fallback}</>
  return <>{children}</>
}
